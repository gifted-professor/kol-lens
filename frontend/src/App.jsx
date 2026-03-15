
import React, { useState, useEffect } from 'react';

const API_BASE = `${window.location.protocol}//${window.location.hostname}:5001/api`;
const JOB_POLL_INTERVAL_MS = 800;
const JOB_POLL_RETRY_DELAYS_MS = [1000, 2000, 4000];

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function getProfileStageLabel(status, reason, softFlags = []) {
  const hasSoftFlags = Array.isArray(softFlags) && softFlags.length > 0;
  if (status === 'Pass' && hasSoftFlags) return '通过初筛（带提示）';
  if (status === 'Pass') return '通过初筛';
  if (status === 'Missing' || reason === 'No data returned by scraper' || reason === '采集器未返回该账号数据') return '未返回数据';
  if (status === 'Reject') return '未通过初筛';
  return status || '未知状态';
}

function formatReviewReason(reason) {
  if (!reason) return '';
  if (reason === 'No data returned by scraper') return '本次未返回数据';
  if (reason === '采集器未返回该账号数据') return '本次未返回数据';
  if (reason === 'No data') return '未抓取到数据';
  if (reason === '未抓取到数据') return '未抓取到数据';
  if (reason === 'No posts') return '账号没有可用帖子';
  if (reason === '账号没有可用帖子') return '账号没有可用帖子';
  if (reason === 'Inactive (> 30 days)') return '近 30 天无更新';
  if (reason === '近 30 天无更新') return '近 30 天无更新';
  if (reason === 'Too much paid content') return '近期付费内容占比过高';
  if (reason === '近期付费内容占比过高') return '近期付费内容占比过高';
  if (reason === 'Toxic bioLink') return '主页外链命中排雷规则';
  if (reason === 'Toxic keywords in text/hashtags/bio') return '文案或标签命中排雷规则';
  return reason;
}

function formatVisualReviewSummary(review) {
  if (!review || review.success === false) {
    return review?.error || '';
  }

  const reason = (review.reason || '').trim();
  const signals = Array.isArray(review.signals)
    ? review.signals.map((item) => String(item || '').trim()).filter(Boolean)
    : [];

  if (!reason && signals.length === 0) return '';
  if (signals.length === 0) return reason;
  if (!reason) return `[${signals.join('；')}]`;

  const normalizedReason = reason.replace(/[。；\s]+$/, '');
  return `${normalizedReason} [${signals.join('；')}]`;
}

function formatSoftFlag(flag) {
  if (!flag) return '';
  if (typeof flag === 'string') return flag;

  const keyword = String(flag.keyword || '').trim();
  const source = String(flag.source || '').trim();

  if (keyword && source) return `"${keyword}"@${source}`;
  if (keyword) return `"${keyword}"`;
  if (source) return source;
  return '';
}

function formatSoftFlags(flags) {
  if (!Array.isArray(flags) || flags.length === 0) return '';
  const formatted = flags.map((item) => formatSoftFlag(item)).filter(Boolean);
  if (formatted.length === 0) return '';
  return `文本提示：[${formatted.join('；')}]`;
}

function ProfileLink({ url }) {
  if (!url) {
    return <>无链接</>;
  }

  return (
    <a href={url} target="_blank" rel="noreferrer" style={{ color: '#0d6efd', textDecoration: 'underline' }}>
      {url}
    </a>
  );
}

function formatJobStatus(status) {
  if (status === 'queued') return '排队中';
  if (status === 'running') return '运行中';
  if (status === 'completed') return '已完成';
  if (status === 'failed') return '失败';
  if (status === 'cancelled') return '已取消';
  return status || '未知';
}

function formatJobStage(stage) {
  const stageMap = {
    submitting: '提交中',
    queued: '排队中',
    starting: '开始',
    preparing: '准备中',
    scraping: '采集中',
    apify_start: '提交任务',
    apify_running: 'Apify 运行中',
    downloading: '下载结果',
    filtering: '初筛中',
    batch_preparing: '准备批次',
    batch_completed: '批次完成',
    batch_failed: '批次失败',
    visual_reviewing: '视觉复核中',
    completed: '完成',
    failed: '失败',
    cancelled: '已取消',
  };
  return stageMap[stage] || stage || '未知';
}

function formatTargetPreview(job) {
  const targets = Array.isArray(job?.current_targets)
    ? job.current_targets.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  const total = typeof job?.current_target_count === 'number' ? job.current_target_count : targets.length;

  if (targets.length === 0 || total === 0) return '';
  if (total > targets.length) {
    return `${targets.join('，')} 等 ${total} 个`;
  }
  return targets.join('，');
}

function getProfileCardTone(status, softFlags = []) {
  const hasSoftFlags = Array.isArray(softFlags) && softFlags.length > 0;
  if (status === 'Pass' && hasSoftFlags) {
    return {
      accent: '#f0ad4e',
      badgeBackground: '#fff3cd',
      badgeColor: '#856404',
      label: '通过初筛（带提示）',
      icon: '🟡'
    };
  }
  if (status === 'Pass') {
    return {
      accent: '#198754',
      badgeBackground: '#d1e7dd',
      badgeColor: '#0f5132',
      label: '通过初筛',
      icon: '🟢'
    };
  }
  if (status === 'Missing') {
    return {
      accent: '#6c757d',
      badgeBackground: '#e9ecef',
      badgeColor: '#495057',
      label: '未返回数据',
      icon: '⚪'
    };
  }
  return {
    accent: '#dc3545',
    badgeBackground: '#f8d7da',
    badgeColor: '#842029',
    label: '未通过初筛',
    icon: '🔴'
  };
}

function summarizePassReason(reason) {
  const normalized = formatReviewReason(reason);
  if (!normalized) return '';

  const clauses = normalized
    .split(/[；;]+/)
    .map((item) => item.trim())
    .filter(Boolean);

  const summary = [];
  for (const clause of clauses) {
    if (clause.includes('已提取') && clause.includes('封面')) {
      continue;
    }
    if (clause.includes('未命中硬性外链/文本排雷规则') || clause.includes('未命中竞品/怀孕类关键词')) {
      continue;
    }
    if (clause.includes('未命中硬性排雷规则')) {
      summary.push('未命中排雷规则');
      continue;
    }
    summary.push(clause);
  }

  const deduped = summary.filter((item, index) => summary.indexOf(item) === index);
  if (deduped.length === 0) {
    return normalized;
  }
  return deduped.slice(0, 2).join('，');
}

function formatReasonSummary(item) {
  const normalized = formatReviewReason(item?.reason);
  if (!normalized) return '';

  if (item?.status === 'Pass') {
    return summarizePassReason(normalized);
  }
  return normalized;
}

function needsExpansion(item) {
  if (!item?.reason) return false;
  const normalized = formatReviewReason(item.reason);
  const summary = formatReasonSummary(item);
  return Boolean(normalized && summary && normalized !== summary);
}

function formatShortProfileUrl(url) {
  if (!url) return '无链接';
  try {
    const parsed = new URL(url);
    const pathname = parsed.pathname.replace(/\/+$/, '') || '/';
    const segments = pathname.split('/').filter(Boolean);
    const shortPath = segments.map((segment, index) => {
      if (index === segments.length - 1 && segment.length > 12) {
        return `${segment.slice(0, 8)}...`;
      }
      return segment;
    }).join('/');
    return `${parsed.hostname}/${shortPath}`;
  } catch {
    const compact = String(url).replace(/^https?:\/\//, '');
    if (compact.length <= 36) return compact;
    return `${compact.slice(0, 33)}...`;
  }
}

function App() {
  const [activeTab, setActiveTab] = useState('tiktok');
  const [submitting, setSubmitting] = useState(false);
  const [scrapeRunning, setScrapeRunning] = useState(false);
  const [visualLoading, setVisualLoading] = useState(false);
  const [scrapeJob, setScrapeJob] = useState(null);
  const [visualJob, setVisualJob] = useState(null);
  const [abortController, setAbortController] = useState(null);
  const [result, setResult] = useState(null);
  const [resultPlatform, setResultPlatform] = useState(null);
  const [error, setError] = useState(null);
  const [visualError, setVisualError] = useState(null);
  const [tableData, setTableData] = useState([]);
  const [visualResults, setVisualResults] = useState({});
  const [visualProgress, setVisualProgress] = useState({ done: 0, total: 0 });
  const [expandedCards, setExpandedCards] = useState(() => new Set());

  // Form states
  const [tiktokProfiles, setTiktokProfiles] = useState('');
  const [tiktokLimit, setTiktokLimit] = useState(20);
  const [tiktokOptions, setTiktokOptions] = useState({
    downloadVideos: false,
    downloadCovers: false,
    downloadAvatars: false,
    excludePinnedPosts: false
  });

  const [instagramUsernames, setInstagramUsernames] = useState('');
  const [instagramOptions, setInstagramOptions] = useState({
    includeAbout: false
  });

  const [youtubeQuery, setYoutubeQuery] = useState('');
  const [youtubeLimit, setYoutubeLimit] = useState(10);
  const [youtubeMode, setYoutubeMode] = useState('search'); // search or channel
  const [youtubeOptions, setYoutubeOptions] = useState({
    downloadSubtitles: false,
    hasCC: false
  });

  // File upload state
  // eslint-disable-next-line no-unused-vars
  const [file, setFile] = useState(null);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploading, setUploading] = useState(false);

  // Scraping state
  const [forceRefresh, setForceRefresh] = useState(false);
  
  // Full datasets from upload
  const [fullTiktokProfiles, setFullTiktokProfiles] = useState([]);
  const [fullInstagramUsernames, setFullInstagramUsernames] = useState([]);
  const [fullYoutubeQueries, setFullYoutubeQueries] = useState([]);
  
  // Batch limit slider state
  const [batchLimit, setBatchLimit] = useState(5); // Default to 5 profiles

  useEffect(() => {
    setError(null);
    setVisualError(null);
    setExpandedCards(new Set());
  }, [activeTab]);

  useEffect(() => () => {
    abortController?.abort();
  }, [abortController]);

  // Update displayed inputs when batch limit or full data changes
  useEffect(() => {
    if (fullTiktokProfiles.length > 0) {
        setTiktokProfiles(fullTiktokProfiles.slice(0, batchLimit).join(', '));
    }
    if (fullInstagramUsernames.length > 0) {
        setInstagramUsernames(fullInstagramUsernames.slice(0, batchLimit).join(', '));
    }
    if (fullYoutubeQueries.length > 0) {
        setYoutubeQuery(fullYoutubeQueries.slice(0, batchLimit).join(', '));
    }
  }, [batchLimit, fullTiktokProfiles, fullInstagramUsernames, fullYoutubeQueries]);

  const handleFileUpload = async (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;
    
    setFile(selectedFile);
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    setUploading(true);
    try {
      const response = await fetch(`${API_BASE}/upload`, {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      if (data.success) {
        setUploadResult(data);
        
        // Process and store FULL lists
        if (data.grouped_data.tiktok.length > 0) {
            const tiktokList = data.grouped_data.tiktok.map(u => {
                try {
                    const url = new URL(u);
                    const pathParts = url.pathname.split('/');
                    const userPart = pathParts.find(p => p.startsWith('@'));
                    return userPart ? userPart.substring(1) : u;
                } catch { return u; }
            });
            setFullTiktokProfiles(tiktokList);
        }
        
        if (data.grouped_data.instagram.length > 0) {
             const instaList = data.grouped_data.instagram.map(u => {
                try {
                    const url = new URL(u);
                    const pathParts = url.pathname.split('/').filter(Boolean);
                    return pathParts.length > 0 ? pathParts[0] : u;
                } catch { return u; }
             });
             setFullInstagramUsernames(instaList);
        }
        
        if (data.grouped_data.youtube.length > 0) {
            setYoutubeMode('channel');
            setFullYoutubeQueries(data.grouped_data.youtube);
        }
      } else {
        setError(data.error);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleScrape = async () => {
    if (scrapeRunning || submitting) {
      return;
    }

    const requestedPlatform = activeTab;
    const controller = new AbortController();
    let lastPartialSignature = '';

    setSubmitting(true);
    setScrapeRunning(true);
    setAbortController(controller);
    setError(null);
    setVisualError(null);
    setScrapeJob({
      id: null,
      type: 'scrape',
      platform: requestedPlatform,
      status: 'queued',
      stage: 'submitting',
      message: '提交中...',
      progress: { done: 0, total: null }
    });
    
    try {
      let payload = {};

      if (requestedPlatform === 'tiktok') {
        // Apply batch limit to profiles list
        const profiles = tiktokProfiles.split(',').map(s => s.trim()).filter(Boolean);
        const limitedProfiles = profiles.slice(0, batchLimit);
        
        payload = {
          profiles: limitedProfiles,
          limit: tiktokLimit,
          forceRefresh,
          ...tiktokOptions
        };
      } else if (requestedPlatform === 'instagram') {
        const usernames = instagramUsernames.split(',').map(s => s.trim()).filter(Boolean);
        const limitedUsernames = usernames.slice(0, batchLimit);
        
        payload = {
          usernames: limitedUsernames,
          forceRefresh,
          ...instagramOptions
        };
      } else if (requestedPlatform === 'youtube') {
        payload = {
          mode: youtubeMode,
          limit: youtubeLimit,
          forceRefresh,
          ...youtubeOptions
        };
        if (youtubeMode === 'search') {
          // Search queries are not typically batched per profile, but per query
          // If user inputs multiple queries, we can limit them
          const queries = youtubeQuery.split(',').map(s => s.trim()).filter(Boolean);
          payload.queries = queries.slice(0, batchLimit);
        } else {
          const urls = youtubeQuery.split(',').map(s => s.trim()).filter(Boolean);
          payload.urls = urls.slice(0, batchLimit);
        }
      }

      const response = await fetch(`${API_BASE}/jobs/scrape`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          platform: requestedPlatform,
          payload
        })
      });
      
      const data = await response.json();
      if (!response.ok || !data.success) {
        setScrapeJob((currentJob) => currentJob ? {
          ...currentJob,
          status: 'failed',
          stage: 'failed',
          message: data.error || 'Unknown error occurred'
        } : currentJob);
        setScrapeRunning(false);
        setError(data.error || 'Unknown error occurred');
        return;
      }

      setScrapeJob(data.job || null);
      const finalJob = await pollJobUntilDone(data.job?.id, (job) => {
        setScrapeJob(job);

        const partialResult = job?.partial_result;
        const partialSignature = partialResult
          ? `${job.progress?.done || 0}:${partialResult.count || 0}:${partialResult.profile_reviews?.length || 0}`
          : '';

        if (partialSignature && partialSignature !== lastPartialSignature) {
          lastPartialSignature = partialSignature;
          setResult(partialResult);
          setResultPlatform(requestedPlatform);
          setVisualResults({});
          setVisualProgress({ done: 0, total: 0 });
          setVisualJob(null);
          setExpandedCards(new Set());
          void fetchResults(requestedPlatform);
        }
      }, controller.signal);
      if (!finalJob || finalJob.status === 'cancelled') {
        return;
      }

      if (finalJob.status === 'completed') {
        setScrapeJob(finalJob);
        setResult(finalJob.result);
        setResultPlatform(requestedPlatform);
        setVisualResults({});
        setVisualProgress({ done: 0, total: 0 });
        setVisualJob(null);
        setExpandedCards(new Set());
        setScrapeRunning(false);
        await fetchResults(requestedPlatform);
      } else {
        setScrapeRunning(false);
        setError(finalJob.error || '采集任务失败');
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        return;
      }
      setScrapeRunning(false);
      setError(err.message);
    } finally {
      setSubmitting(false);
      setAbortController((currentController) => (
        currentController === controller ? null : currentController
      ));
    }
  };

  const handleCancelScrape = async () => {
    const currentJobId = scrapeJob?.id;
    const currentController = abortController;

    currentController?.abort();
    setAbortController(null);
    setSubmitting(false);
    setScrapeRunning(false);

    if (!currentJobId) {
      setScrapeJob((currentJob) => currentJob ? {
        ...currentJob,
        status: 'cancelled',
        stage: 'cancelled',
        message: '已取消提交'
      } : currentJob);
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/jobs/${currentJobId}/cancel`, {
        method: 'POST'
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || '取消采集失败');
      }
      setScrapeJob((currentJob) => currentJob ? {
        ...currentJob,
        status: 'cancelled',
        stage: 'cancelled',
        message: '用户取消'
      } : currentJob);
    } catch (err) {
      setScrapeJob((currentJob) => currentJob ? {
        ...currentJob,
        status: 'cancelled',
        stage: 'cancelled',
        message: '本地已停止等待，后端可能仍在执行'
      } : currentJob);
      setError(err.message);
    }
  };

  const pollJobUntilDone = async (jobId, onUpdate, signal) => {
    if (!jobId) {
      throw new Error('Missing job id');
    }

    let retries = 0;

    while (true) {
      if (signal?.aborted) {
        return null;
      }

      try {
        const response = await fetch(`${API_BASE}/jobs/${jobId}`, { signal });
        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data.error || 'Job polling failed');
        }

        retries = 0;
        const job = data.job;
        if (typeof onUpdate === 'function') {
          onUpdate(job);
        }

        if (job.status === 'completed' || job.status === 'failed' || job.status === 'cancelled') {
          return job;
        }
      } catch (err) {
        if (err.name === 'AbortError') {
          return null;
        }
        if (retries >= JOB_POLL_RETRY_DELAYS_MS.length) {
          throw err;
        }
        const retryDelay = JOB_POLL_RETRY_DELAYS_MS[retries];
        retries += 1;
        await sleep(retryDelay);
        continue;
      }

      await sleep(JOB_POLL_INTERVAL_MS);
    }
  };

  const fetchResults = async (platform = activeTab) => {
    try {
      const response = await fetch(`${API_BASE}/results/${platform}`);
      const data = await response.json();
      setTableData(data);
    } catch (err) {
      console.error("Failed to fetch results", err);
    }
  };

  const downloadFile = (format) => {
    const platform = resultPlatform || activeTab;
    window.location.href = `${API_BASE}/download/${platform}/${format}`;
  };

  const downloadImageReview = () => {
    const platform = resultPlatform || activeTab;
    window.location.href = `${API_BASE}/download/${platform}/image-review`;
  };

  const handleVisualReview = async () => {
    const candidates = (result?.profile_reviews || []).filter(
      (item) => item.status === 'Pass' && Array.isArray(item.covers) && item.covers.length > 0
    );

    if (candidates.length === 0) {
      setVisualError('当前没有可进行视觉复核的博主。');
      return;
    }

    setVisualLoading(true);
    setVisualError(null);
    setVisualResults({});
    setVisualProgress({ done: 0, total: candidates.length });
    setVisualJob(null);

    try {
      const response = await fetch(`${API_BASE}/jobs/visual-review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profiles: candidates.map((item) => ({
            username: item.username,
            covers: item.covers
          }))
        })
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || '视觉复核任务创建失败');
      }

      setVisualJob(data.job || null);
      const finalJob = await pollJobUntilDone(data.job?.id, (job) => {
        setVisualJob(job);
        if (job?.progress) {
          setVisualProgress({
            done: job.progress.done || 0,
            total: job.progress.total || candidates.length,
          });
        }
      });

      if (finalJob.status === 'completed') {
        setVisualJob(finalJob);
        setVisualResults(finalJob.result?.visual_results || {});
      } else {
        throw new Error(finalJob.error || '视觉复核失败');
      }
    } catch (err) {
      setVisualError(err.message);
    } finally {
      setVisualLoading(false);
    }
  };

  const renderJobCard = (title, job, tone = 'info') => {
    if (!job) return null;

    const palette = tone === 'warning'
      ? { background: '#fff3cd', border: '#ffe69c', color: '#856404' }
      : { background: '#e9f2ff', border: '#b6d4fe', color: '#084298' };
    const done = job.progress?.done ?? 0;
    const total = job.progress?.total;
    const hasDeterminateProgress = typeof total === 'number' && total > 0;
    const progressPercent = hasDeterminateProgress
      ? Math.max(5, Math.min(100, Math.round((done / total) * 100)))
      : null;
    const targetPreview = formatTargetPreview(job);

    return (
      <div style={{ marginTop: '20px', padding: '15px', backgroundColor: palette.background, color: palette.color, borderRadius: '5px', border: `1px solid ${palette.border}` }}>
        <p style={{ margin: '0 0 8px 0' }}><strong>{title}</strong></p>
        <p style={{ margin: '0 0 6px 0' }}>状态：{formatJobStatus(job.status)} | 阶段：{formatJobStage(job.stage)}</p>
        <p style={{ margin: '0 0 8px 0' }}>{job.message}</p>
        <div style={{ width: '100%', height: '10px', backgroundColor: '#ffffff', borderRadius: '999px', overflow: 'hidden', border: '1px solid rgba(0,0,0,0.08)' }}>
          {hasDeterminateProgress ? (
            <div style={{ width: `${progressPercent}%`, height: '100%', backgroundColor: tone === 'warning' ? '#f0ad4e' : '#0d6efd', transition: 'width 0.5s ease' }} />
          ) : (
            <div style={{ width: '35%', height: '100%', backgroundColor: tone === 'warning' ? '#f0ad4e' : '#0d6efd', animation: 'pulseBar 1.2s ease-in-out infinite' }} />
          )}
        </div>
        {hasDeterminateProgress ? (
          <p style={{ margin: '8px 0 0 0' }}>总批次进度：已完成 {done} / {total}</p>
        ) : (
          <p style={{ margin: '8px 0 0 0' }}>当前进度待回传...</p>
        )}
        {typeof job.batch_index === 'number' && typeof job.batch_total === 'number' && (
          <p style={{ margin: '8px 0 0 0' }}>当前批次：第 {job.batch_index} / {job.batch_total} 批</p>
        )}
        {targetPreview && <p style={{ margin: '8px 0 0 0' }}>本批账号：{targetPreview}</p>}
        {job.current_username && <p style={{ margin: '8px 0 0 0' }}>当前对象：{job.current_username}</p>}
        {(typeof job.passed_count === 'number' || typeof job.rejected_count === 'number' || typeof job.failed_count === 'number') && (
          <p style={{ margin: '8px 0 0 0' }}>
            已处理结果：
            通过 {job.passed_count || 0}
            ，拒绝 {job.rejected_count || 0}
            ，失败 {job.failed_count || 0}
          </p>
        )}
      </div>
    );
  };

  const toggleCardExpansion = (cardKey) => {
    setExpandedCards((current) => {
      const next = new Set(current);
      if (next.has(cardKey)) {
        next.delete(cardKey);
      } else {
        next.add(cardKey);
      }
      return next;
    });
  };

  const renderProfileCards = () => {
    const profileReviews = Array.isArray(result?.profile_reviews) ? result.profile_reviews : [];
    if (profileReviews.length === 0) return null;

    const statusRank = {
      Reject: 0,
      Missing: 1,
      PassSoft: 2,
      Pass: 3,
    };

    const sortedReviews = [...profileReviews].sort((left, right) => {
      const leftRank = left.status === 'Pass' && (left.soft_flags?.length || 0) > 0 ? statusRank.PassSoft : (statusRank[left.status] ?? 9);
      const rightRank = right.status === 'Pass' && (right.soft_flags?.length || 0) > 0 ? statusRank.PassSoft : (statusRank[right.status] ?? 9);
      return leftRank - rightRank;
    });

    const passedCount = profileReviews.filter((item) => item.status === 'Pass').length;
    const rejectedCount = profileReviews.filter((item) => item.status !== 'Pass').length;
    const requestedTotal = result?.requested_total || result.filter_stats?.original_profiles || profileReviews.length;

    return (
      <div style={{ marginTop: '10px', padding: '12px', backgroundColor: '#fff', color: '#333', borderRadius: '8px', border: '1px solid #c3e6cb' }}>
        {result?.is_partial ? (
          <p style={{ margin: '0 0 12px 0' }}>
            <strong>当前进度：</strong>
            已返回 {profileReviews.length} / {requestedTotal} 个博主的初筛结果，
            当前通过 {passedCount} 个，
            筛掉 {rejectedCount} 个。
          </p>
        ) : (
          <p style={{ margin: '0 0 12px 0' }}>
            <strong>筛选统计：</strong>
            请求博主 {requestedTotal} 个，
            通过 {passedCount} 个，
            筛掉 {rejectedCount} 个。
          </p>
        )}
        <div style={{ display: 'grid', gap: '12px' }}>
          {sortedReviews.map((item, index) => {
            const cardKey = `${item.username || 'unknown'}-${index}`;
            const expanded = expandedCards.has(cardKey);
            const tone = getProfileCardTone(item.status, item.soft_flags);
            const fullReason = formatReviewReason(item.reason);
            const summaryReason = formatReasonSummary(item);
            const showExpansion = needsExpansion(item);
            const displayReason = expanded || !showExpansion ? fullReason : summaryReason;
            const softFlagsText = Array.isArray(item.soft_flags)
              ? item.soft_flags.map((flag) => formatSoftFlag(flag)).filter(Boolean)
              : [];

            return (
              <div
                key={cardKey}
                style={{
                  borderLeft: `5px solid ${tone.accent}`,
                  borderRadius: '10px',
                  border: '1px solid #e5e7eb',
                  padding: '14px 16px',
                  backgroundColor: '#ffffff',
                  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'flex-start' }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
                      <strong style={{ fontSize: '16px', color: '#111827' }}>
                        {tone.icon} {item.username || '未知账号'}
                      </strong>
                      <span style={{ backgroundColor: tone.badgeBackground, color: tone.badgeColor, borderRadius: '999px', padding: '3px 10px', fontSize: '12px', fontWeight: 600 }}>
                        {tone.label}
                      </span>
                      {softFlagsText.map((flagText) => (
                        <span key={`${cardKey}-${flagText}`} style={{ backgroundColor: '#fff3cd', color: '#856404', borderRadius: '999px', padding: '3px 10px', fontSize: '12px', fontWeight: 500 }}>
                          {flagText}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span style={{ flexShrink: 0, backgroundColor: '#f3f4f6', color: '#374151', borderRadius: '999px', padding: '4px 10px', fontSize: '12px', fontWeight: 600 }}>
                    封面 {item.covers?.length || 0}
                  </span>
                </div>

                {displayReason && (
                  <div style={{ marginTop: '10px', color: '#374151', lineHeight: 1.6 }}>
                    <span>{displayReason}</span>
                    {showExpansion && (
                      <button
                        onClick={() => toggleCardExpansion(cardKey)}
                        style={{
                          marginLeft: '8px',
                          border: 'none',
                          background: 'none',
                          color: '#0d6efd',
                          cursor: 'pointer',
                          padding: 0,
                          fontSize: '13px',
                          fontWeight: 600
                        }}
                      >
                        {expanded ? '收起详情' : '展开详情'}
                      </button>
                    )}
                  </div>
                )}

                <div style={{ marginTop: '10px', fontSize: '13px' }}>
                  {item.profile_url ? (
                    <a href={item.profile_url} target="_blank" rel="noreferrer" style={{ color: '#0d6efd', textDecoration: 'underline' }}>
                      🔗 {formatShortProfileUrl(item.profile_url)}
                    </a>
                  ) : (
                    <span style={{ color: '#6b7280' }}>🔗 无链接</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  // Helper to render table rows based on platform
  const renderTable = () => {
    if (!tableData || tableData.length === 0) return null;

    const displayPlatform = resultPlatform || activeTab;
    let headers = [];
    let rowRenderer = null;

    if (displayPlatform === 'tiktok') {
      headers = ['ID', 'Author', 'Text', 'Created', 'Views', 'Likes'];
      rowRenderer = (item) => (
        <tr key={item.id}>
          <td>{item.id}</td>
          <td>{item.authorMeta?.name}</td>
          <td>{item.text?.substring(0, 50)}...</td>
          <td>{item.createTimeISO?.split('T')[0]}</td>
          <td>{item.playCount}</td>
          <td>{item.diggCount}</td>
        </tr>
      );
    } else if (displayPlatform === 'instagram') {
      headers = ['Username', 'Full Name', 'Followers', 'Posts', 'Bio'];
      rowRenderer = (item) => (
        <tr key={item.id || item.username}>
          <td>{item.username}</td>
          <td>{item.fullName}</td>
          <td>{item.followersCount}</td>
          <td>{item.postsCount}</td>
          <td>{item.biography?.substring(0, 50)}...</td>
        </tr>
      );
    } else if (displayPlatform === 'youtube') {
      headers = ['Title', 'Channel', 'Views', 'Date', 'Duration'];
      rowRenderer = (item) => (
        <tr key={item.id}>
          <td><a href={item.url} target="_blank" rel="noopener noreferrer">{item.title?.substring(0, 40)}...</a></td>
          <td>{item.channelName}</td>
          <td>{item.viewCount}</td>
          <td>{item.date?.split('T')[0]}</td>
          <td>{item.duration}</td>
        </tr>
      );
    }

    return (
      <div style={{ marginTop: '20px', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid #ddd' }}>
          <thead>
            <tr style={{ backgroundColor: '#f8f9fa', textAlign: 'left' }}>
              {headers.map(h => <th key={h} style={{ padding: '10px', borderBottom: '1px solid #ddd' }}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {tableData.slice(0, 10).map((item) => ( // Show top 10
              rowRenderer(item)
            ))}
          </tbody>
        </table>
        {tableData.length > 10 && <p style={{ textAlign: 'center', color: '#666' }}>Showing top 10 of {tableData.length} results...</p>}
      </div>
    );
  };

  return (
    <div style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto', fontFamily: 'Arial, sans-serif' }}>
      <style>{`
        @keyframes pulseBar {
          0% { opacity: 0.35; }
          50% { opacity: 1; }
          100% { opacity: 0.35; }
        }
      `}</style>
      <h1>🎥 社交媒体数据采集器 (Social Media Scraper)</h1>
      
      {/* Tabs */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        {['tiktok', 'instagram', 'youtube'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 20px',
              cursor: 'pointer',
              backgroundColor: activeTab === tab ? '#007bff' : '#f0f0f0',
              color: activeTab === tab ? 'white' : 'black',
              border: 'none',
              borderRadius: '5px',
              textTransform: 'capitalize'
            }}
          >
            {tab === 'tiktok' ? 'TikTok' : tab === 'instagram' ? 'Instagram' : 'YouTube'}
          </button>
        ))}
      </div>

      {/* File Upload Section */}
      <div style={{ marginBottom: '20px', padding: '15px', border: '2px dashed #ccc', borderRadius: '5px', textAlign: 'center' }}>
        <h3>📁 上传 Excel 文件</h3>
        <p>上传文件以自动识别平台并填充输入框。</p>
        <input 
          type="file" 
          accept=".xlsx, .xls"
          onChange={handleFileUpload}
          disabled={uploading}
          style={{ marginBottom: '10px' }}
        />
        {uploading && !uploadResult && <p>正在处理文件...</p>}
        {uploadResult && (
          <div style={{ marginTop: '10px', textAlign: 'left', backgroundColor: '#e9ecef', padding: '10px', borderRadius: '5px' }}>
            <p><strong>分析结果:</strong></p>
            <ul>
              <li>TikTok 链接数: {uploadResult.stats.TikTok || 0}</li>
              <li>Instagram 链接数: {uploadResult.stats.Instagram || 0}</li>
              <li>YouTube 链接数: {uploadResult.stats.YouTube || 0}</li>
              <li>未知/无效链接: {uploadResult.stats.Unknown || 0}</li>
            </ul>
            <p style={{ color: 'green', fontSize: '0.9em' }}>✔ 已根据文件内容自动填充输入框！</p>
          </div>
        )}
      </div>

      {/* Batch Limit Slider */}
      <div style={{ marginBottom: '20px', padding: '15px', border: '1px solid #ddd', borderRadius: '5px', backgroundColor: '#f9f9f9' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <label style={{ fontWeight: 'bold' }}>🔢 本次抓取数量 (批量大小):</label>
          <span style={{ fontSize: '1.2em', color: '#007bff', fontWeight: 'bold' }}>{batchLimit}</span>
        </div>
        <input 
          type="range" 
          min="1" 
          max="100" 
          value={batchLimit} 
          onChange={(e) => setBatchLimit(parseInt(e.target.value))}
          style={{ width: '100%', cursor: 'pointer' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '5px' }}>
            <p style={{ fontSize: '0.8em', color: '#666', margin: 0 }}>
            拖动滑块选择本次要从列表中处理多少个博主/链接 (最大: 100)。
            </p>
            <label style={{ fontSize: '0.9em', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                <input 
                    type="checkbox" 
                    checked={forceRefresh} 
                    onChange={e => setForceRefresh(e.target.checked)} 
                    style={{ marginRight: '5px' }}
                /> 
                强制刷新缓存 (重新采集)
            </label>
        </div>
      </div>

      {/* Forms */}
      <div style={{ border: '1px solid #ddd', padding: '20px', borderRadius: '5px' }}>
        {activeTab === 'tiktok' && (
          <div>
            <h3>TikTok 采集配置</h3>
            <div style={{ marginBottom: '10px' }}>
              <label>用户名列表 (逗号分隔):</label>
              <input 
                type="text" 
                value={tiktokProfiles}
                onChange={e => setTiktokProfiles(e.target.value)}
                placeholder="_lilheat_, brooklynreviewsxoxo"
                style={{ width: '100%', padding: '8px', marginTop: '5px' }}
              />
            </div>
            <div style={{ marginBottom: '10px' }}>
              <label>单账号抓取上限 (Limit per profile):</label>
              <input 
                type="number" 
                value={tiktokLimit}
                onChange={e => setTiktokLimit(e.target.value)}
                style={{ width: '100px', marginLeft: '10px', padding: '5px' }}
              />
            </div>
            <div style={{ display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
              <label><input type="checkbox" checked={tiktokOptions.excludePinnedPosts} onChange={e => setTiktokOptions({...tiktokOptions, excludePinnedPosts: e.target.checked})} /> 排除置顶视频 (Pinned)</label>
              <label><input type="checkbox" checked={tiktokOptions.downloadVideos} onChange={e => setTiktokOptions({...tiktokOptions, downloadVideos: e.target.checked})} /> 下载视频文件</label>
              <label><input type="checkbox" checked={tiktokOptions.downloadCovers} onChange={e => setTiktokOptions({...tiktokOptions, downloadCovers: e.target.checked})} /> 下载封面图</label>
              <label><input type="checkbox" checked={tiktokOptions.downloadAvatars} onChange={e => setTiktokOptions({...tiktokOptions, downloadAvatars: e.target.checked})} /> 下载头像</label>
            </div>
          </div>
        )}

        {activeTab === 'instagram' && (
          <div>
            <h3>Instagram 采集配置</h3>
            <div style={{ marginBottom: '10px' }}>
              <label>用户名列表 (逗号分隔):</label>
              <input 
                type="text" 
                value={instagramUsernames}
                onChange={e => setInstagramUsernames(e.target.value)}
                placeholder="babeidii, kuleshova"
                style={{ width: '100%', padding: '8px', marginTop: '5px' }}
              />
            </div>
            <div>
              <label><input type="checkbox" checked={instagramOptions.includeAbout} onChange={e => setInstagramOptions({...instagramOptions, includeAbout: e.target.checked})} /> 包含详细简介 (About Section)</label>
            </div>
          </div>
        )}

        {activeTab === 'youtube' && (
          <div>
            <h3>YouTube 采集配置</h3>
            <div style={{ marginBottom: '10px' }}>
              <label>模式:</label>
              <select value={youtubeMode} onChange={e => setYoutubeMode(e.target.value)} style={{ marginLeft: '10px', padding: '5px' }}>
                <option value="search">关键词搜索 (Search)</option>
                <option value="channel">频道/视频链接 (Channel/URL)</option>
              </select>
            </div>
            <div style={{ marginBottom: '10px' }}>
              <label>{youtubeMode === 'search' ? '关键词' : '链接'} (逗号分隔):</label>
              <input 
                type="text" 
                value={youtubeQuery}
                onChange={e => setYoutubeQuery(e.target.value)}
                placeholder={youtubeMode === 'search' ? "Crawlee, Apify" : "https://youtube.com/@Channel"}
                style={{ width: '100%', padding: '8px', marginTop: '5px' }}
              />
            </div>
            <div style={{ marginBottom: '10px' }}>
              <label>结果数量限制:</label>
              <input 
                type="number" 
                value={youtubeLimit}
                onChange={e => setYoutubeLimit(e.target.value)}
                style={{ width: '100px', marginLeft: '10px', padding: '5px' }}
              />
            </div>
            <div style={{ display: 'flex', gap: '15px' }}>
              <label><input type="checkbox" checked={youtubeOptions.downloadSubtitles} onChange={e => setYoutubeOptions({...youtubeOptions, downloadSubtitles: e.target.checked})} /> 下载字幕</label>
              <label><input type="checkbox" checked={youtubeOptions.hasCC} onChange={e => setYoutubeOptions({...youtubeOptions, hasCC: e.target.checked})} /> 仅限有字幕视频 (CC)</label>
            </div>
          </div>
        )}

        <div style={{ marginTop: '20px', display: 'flex', gap: '10px' }}>
          <button 
            onClick={scrapeRunning ? handleCancelScrape : handleScrape}
            style={{ 
              padding: '10px 20px', 
              backgroundColor: scrapeRunning ? '#dc3545' : '#28a745',
              color: 'white', 
              border: 'none', 
              borderRadius: '5px',
              fontSize: '16px',
              cursor: 'pointer'
            }}
          >
            {scrapeRunning ? (scrapeJob?.id ? '取消采集' : '取消提交') : '开始采集 (Start Scraping)'}
          </button>
        </div>
      </div>

      {/* Results */}
      {error && (
        <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#f8d7da', color: '#721c24', borderRadius: '5px' }}>
          <strong>错误:</strong> {error}
        </div>
      )}

      {visualError && (
        <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#fff3cd', color: '#856404', borderRadius: '5px' }}>
          <strong>视觉复核提示:</strong> {visualError}
        </div>
      )}

      {renderJobCard('采集任务进度', scrapeJob, 'info')}
      {renderJobCard('视觉复核任务进度', visualJob, 'warning')}

      {result && (
        <div style={{ marginTop: '20px', padding: '15px', backgroundColor: '#d4edda', color: '#155724', borderRadius: '5px' }}>
          <h3>
            {scrapeRunning
              ? (result.is_partial ? '🧩 当前已返回部分结果' : '🕘 当前显示上一次结果')
              : (result.cached ? '🗂️ 已加载缓存结果' : '✅ 采集成功!')}
          </h3>
          <p>
            {scrapeRunning
              ? (
                result.is_partial
                  ? `当前采集仍在进行，下面会逐步展示最新返回的 ${(resultPlatform || activeTab).toUpperCase()} 博主结果。`
                  : `当前采集仍在进行，下面显示的是上一次 ${(resultPlatform || activeTab).toUpperCase()} 结果。`
              )
              : (result.cached ? `当前缓存结果共 ${result.count} 条数据。` : `共采集到 ${result.count} 条数据。`)}
          </p>
          {result.message && (
            <p style={{ marginTop: '8px', marginBottom: 0, color: result.cached ? '#856404' : '#155724' }}>
              {result.message}
            </p>
          )}
          {renderProfileCards()}
          <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
            <button onClick={() => downloadFile('json')} style={{ padding: '8px 15px', cursor: 'pointer' }}>下载 JSON</button>
            <button onClick={() => downloadFile('excel')} style={{ padding: '8px 15px', cursor: 'pointer' }}>下载 Excel</button>
            {result.profile_reviews?.length > 0 && (
              <button onClick={downloadImageReview} style={{ padding: '8px 15px', cursor: 'pointer' }}>
                导出初筛图像表
              </button>
            )}
            {!result.is_partial && result.profile_reviews?.some((item) => item.status === 'Pass' && item.covers?.length > 0) && (
              <button
                onClick={handleVisualReview}
                disabled={visualLoading}
                style={{ padding: '8px 15px', cursor: visualLoading ? 'not-allowed' : 'pointer' }}
              >
                {visualLoading ? '视觉复核进行中...' : '开始视觉复核 (3x3 九宫格)'}
              </button>
            )}
          </div>

          {visualProgress.total > 0 && (
            <p style={{ marginTop: '10px', marginBottom: 0 }}>
              视觉复核进度：{visualProgress.done} / {visualProgress.total}
            </p>
          )}

          {Object.keys(visualResults).length > 0 && (
            <div style={{ marginTop: '12px', padding: '12px', backgroundColor: '#fff', color: '#333', borderRadius: '5px', border: '1px solid #c3e6cb' }}>
              <p style={{ margin: '0 0 8px 0' }}><strong>视觉复核结果：</strong></p>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                {result.profile_reviews
                  ?.filter((item) => visualResults[item.username])
                  .map((item) => {
                    const review = visualResults[item.username];
                    return (
                      <li key={`${item.username}-visual`}>
                        {item.username} | {review.success === false ? '失败' : review.decision}
                        {formatVisualReviewSummary(review) ? `：${formatVisualReviewSummary(review)}` : ''}
                      </li>
                    );
                  })}
              </ul>
            </div>
          )}
          
          {renderTable()}
        </div>
      )}
    </div>
  );

}

export default App;
