
import React, { useState, useEffect } from 'react';
// eslint-disable-next-line no-unused-vars
import { motion, AnimatePresence } from 'framer-motion';
import { UploadCloud, Play, Square, Download, Image as ImageIcon, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, Link as LinkIcon, RefreshCw, XCircle, CheckCircle, AlertCircle, Clock, Youtube, Instagram } from 'lucide-react';

const API_BASE = '/api';
const JOB_POLL_INTERVAL_MS = 800;
const JOB_POLL_RETRY_DELAYS_MS = [1000, 2000, 4000];
const VISUAL_REVIEW_MODE_SIMPLE = 'simple';
const VISUAL_REVIEW_MODE_AUTO = 'auto';
const VISUAL_REVIEW_MODE_ENHANCED = 'enhanced';
const AUTO_ENHANCED_MIN_AVAILABLE_COVERS = 14;
const hoverLiftTransition = { type: 'spring', stiffness: 190, damping: 24, mass: 0.85 };
const bentoVariants = {
  hidden: { opacity: 0, scale: 0.95, y: 20 },
  visible: (index) => ({
    opacity: 1,
    scale: 1,
    y: 0,
    transition: {
      delay: index * 0.08,
      duration: 0.5,
      ease: [0.25, 0.46, 0.45, 0.94],
    },
  }),
};
const bentoCardClassName = 'relative overflow-hidden rounded-[28px] border border-gray-200/60 bg-white p-8 shadow-[0_1px_3px_rgba(15,23,42,0.04),0_20px_60px_rgba(15,23,42,0.05)] transition-[box-shadow,border-color] duration-300 hover:border-gray-300/80 hover:shadow-[0_1px_3px_rgba(15,23,42,0.05),0_20px_48px_rgba(15,23,42,0.08)] md:p-10';
const formFieldClassName = 'w-full rounded-xl border border-gray-200/80 bg-gray-50/80 px-4 py-3 text-sm text-gray-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)] outline-none transition duration-200 placeholder:text-gray-400 focus:border-gray-300 focus:bg-white focus:ring-4 focus:ring-gray-200/70';
const compactFieldClassName = 'w-32 rounded-xl border border-gray-200/80 bg-gray-50/80 px-4 py-3 text-sm text-gray-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)] outline-none transition duration-200 focus:border-gray-300 focus:bg-white focus:ring-4 focus:ring-gray-200/70';
const selectFieldClassName = 'w-full rounded-xl border border-gray-200/80 bg-gray-50/80 px-4 py-3 text-sm text-gray-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)] outline-none transition duration-200 focus:border-gray-300 focus:bg-white focus:ring-4 focus:ring-gray-200/70 md:w-64 appearance-none';
const optionPillClassName = 'flex cursor-pointer items-center gap-2 rounded-xl border border-gray-200/80 bg-gray-50/80 px-4 py-3 text-sm font-medium text-gray-700 transition-[transform,box-shadow,border-color,background-color] duration-200 hover:-translate-y-px hover:border-gray-300 hover:bg-white hover:shadow-[0_8px_18px_rgba(15,23,42,0.05)]';
const TEMPLATE_PLATFORM_LABELS = {
  tiktok: 'TikTok',
  instagram: 'Instagram',
  youtube: 'YouTube',
};
const TEMPLATE_PLACEHOLDER = `【AI 审核目标】
判断该达人是否符合品牌合作标准。

【步骤 1：数据审核】
- 抓取最近前 50 个视频播放量
- 若平均播放量 > 10000 且中位数播放量 > 10000，则通过

【步骤 2：内容场景审核】
- 查看最近前 10 个视频封面
- 判断是否出现以下任一场景：
  A. 室内环境和孩子互动
  B. 手持或展示产品
  C. 与宠物互动
- 若至少出现 1 类场景，则通过

【最终结果】
- 同时满足步骤 1、步骤 2
- 最终判定为“通过”`;

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
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

function normalizeProfileIdentifier(value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return '';

  const tiktokMatch = text.match(/tiktok\.com\/@([^/?#]+)/i);
  if (tiktokMatch?.[1]) return tiktokMatch[1].trim().toLowerCase().replace(/^@+/, '');

  const instagramMatch = text.match(/instagram\.com\/([^/?#]+)/i);
  if (instagramMatch?.[1]) return instagramMatch[1].trim().toLowerCase().replace(/^@+/, '');

  const youtubeMatch = text.match(/youtube\.com\/(?:@|channel\/|c\/|user\/)([^/?#]+)/i);
  if (youtubeMatch?.[1]) return youtubeMatch[1].trim().toLowerCase().replace(/^@+/, '');

  return text.replace(/^@+/, '');
}

function findFailedBatchForProfile(item, failedBatches = []) {
  if (!item || item.status !== 'Missing' || !Array.isArray(failedBatches) || failedBatches.length === 0) {
    return null;
  }

  const candidates = [
    item.username,
    item.profile_url,
    item.upload_metadata?.handle,
    item.upload_metadata?.url,
  ]
    .map((value) => normalizeProfileIdentifier(value))
    .filter(Boolean);

  if (candidates.length === 0) return null;

  return failedBatches.find((batch) => {
    const identifiers = Array.isArray(batch?.identifiers) ? batch.identifiers : [];
    return identifiers.some((value) => candidates.includes(normalizeProfileIdentifier(value)));
  }) || null;
}

function formatFailedBatchReason(batch) {
  if (!batch) return '';
  const batchIndex = typeof batch.batch_index === 'number' ? batch.batch_index : null;
  const batchTotal = typeof batch.batch_total === 'number' ? batch.batch_total : null;
  const errorText = String(batch.error || '').trim();

  if (batchIndex && batchTotal && errorText) {
    return `Apify 第 ${batchIndex}/${batchTotal} 批失败：${errorText}`;
  }
  if (errorText) return `Apify 批次失败：${errorText}`;
  if (batchIndex && batchTotal) return `Apify 第 ${batchIndex}/${batchTotal} 批失败`;
  return 'Apify 批次失败';
}

function buildFailedBatchSummary(failedBatches = []) {
  if (!Array.isArray(failedBatches) || failedBatches.length === 0) return '';
  const batchLabel = failedBatches.length === 1 ? '1 个失败批次' : `${failedBatches.length} 个失败批次`;
  const firstReason = formatFailedBatchReason(failedBatches[0]);
  return firstReason ? `当前有 ${batchLabel}。${firstReason}` : `当前有 ${batchLabel}。`;
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

function formatVisualReviewOutcomeLabel(review) {
  if (!review) return '';
  if (review.success === false) {
    return review.step === 'collage_failed' ? '封面不足' : '失败';
  }
  return review.decision || '';
}

function resolveBackendAssetUrl(path) {
  if (!path) return '';
  if (/^(https?:)?\/\//i.test(path) || path.startsWith('data:')) return path;
  return path.startsWith('/') ? path : `/${path}`;
}

function formatLiveReviewStep(step) {
  const stepMap = {
    preparing: '整理封面',
    collage_loading: '并行加载封面',
    collage_progress: '融合九图中',
    collage_ready: '九宫格就绪',
    collage_failed: '封面不足',
    policy_scan: '检查内容匹配',
    style_scan: '检查风格质感',
    risk_scan: '检查排除项',
    model_wait: '等待模型判定',
    completed: '判定完成',
    failed: '判定失败',
  };
  return stepMap[step] || '视觉复核中';
}

function normalizeLiveReviewLogLines(logLines) {
  if (!Array.isArray(logLines)) return [];

  return logLines
    .map((item, index) => {
      if (typeof item === 'string') {
        const text = item.trim();
        return text ? { id: `legacy-${index}`, text, tone: 'info' } : null;
      }

      const text = String(item?.text || '').trim();
      if (!text) return null;

      return {
        id: String(item?.id || `log-${index}`),
        text,
        tone: String(item?.tone || 'info'),
      };
    })
    .filter(Boolean);
}

function isVisualReviewFinalStep(step) {
  return step === 'completed' || step === 'failed' || step === 'collage_failed';
}

function summarizeVisualReviewRecommendation(candidates) {
  if (!Array.isArray(candidates) || candidates.length === 0) {
    return {
      mode: VISUAL_REVIEW_MODE_AUTO,
      text: '当前没有可进行视觉复核的博主。',
    };
  }

  let strongCount = 0;
  let partialCount = 0;
  candidates.forEach((item) => {
    const coverCount = Array.isArray(item?.covers) ? item.covers.length : 0;
    if (coverCount >= AUTO_ENHANCED_MIN_AVAILABLE_COVERS) {
      strongCount += 1;
    } else if (coverCount >= 10) {
      partialCount += 1;
    }
  });

  if (strongCount >= Math.max(1, Math.ceil(candidates.length * 0.5))) {
    return {
      mode: VISUAL_REVIEW_MODE_ENHANCED,
      text: `当前有 ${strongCount}/${candidates.length} 个账号可用封面达到 ${AUTO_ENHANCED_MIN_AVAILABLE_COVERS} 张以上，适合双九宫格。`,
    };
  }

  if (strongCount === 0 && partialCount === 0) {
    return {
      mode: VISUAL_REVIEW_MODE_SIMPLE,
      text: '当前候选账号大多只有 9 张及以内封面，单九宫格更稳。',
    };
  }

  return {
    mode: VISUAL_REVIEW_MODE_AUTO,
    text: `当前封面数分布不均，其中 ${strongCount} 个账号适合加强复核，建议使用自动推荐并按实际可用图数自动降级。`,
  };
}

function buildResultStateGuidance({
  scrapeRunning,
  result,
  hasVisualReviewCandidates,
  visualReviewCompleted,
  hasFinalReviewExport,
  hasInMemoryFinalReviewData,
  savedFinalReviewArtifactsAvailable,
}) {
  if (!result) return [];

  const showingPreviousResultWhileRunning = Boolean(scrapeRunning && !result.is_partial);
  const guidance = [];

  if (showingPreviousResultWhileRunning) {
    guidance.push({
      key: 'running-previous-result',
      tone: 'info',
      label: '运行中',
      title: '本次抓取仍在执行，当前只是暂时显示上一次可用结果',
      description: '这不代表本次任务已经失败。页面会先保留上一份可查看结果，等本次返回首批数据后再自动切到新结果。',
      nextAction: '请以上方任务进度为准，等待首批结果返回；当前下方数据仅供临时参考。',
    });
    return guidance;
  }

  if (result.is_partial) {
    guidance.push({
      key: 'partial',
      tone: 'info',
      label: '部分结果',
      title: '当前看到的是分批返回的最新结果',
      description: '采集还在继续，当前卡片与统计只代表已经返回的那部分账号。',
      nextAction: savedFinalReviewArtifactsAvailable
        ? '现在可以先导出原始/测试/初筛结果做 spot check；如果需要复用上一次完整复核，也可以直接导出最终复核表。'
        : '现在可以先导出原始/测试/初筛结果做 spot check；等采集完成后再启动视觉复核。',
    });
  }

  if (result.used_fallback) {
    guidance.push({
      key: 'fallback',
      tone: 'warning',
      label: '回退快照',
      title: '当前结果来自后端自动回退的最近一次可用快照',
      description: '这不是本次新抓取到的全新结果，而是后端在当前抓取不可用时保留的最近一次可用数据。',
      nextAction: savedFinalReviewArtifactsAvailable
        ? '可以直接继续导出最终复核表，后端会优先复用已保存的初筛与视觉复核 artifact。'
        : '可以先导出原始/初筛结果做人工核对；如需最新数据，再重新发起抓取。',
    });
  } else if (result.stale_result) {
    guidance.push({
      key: 'stale',
      tone: 'warning',
      label: '旧结果',
      title: '当前结果是最近一次可用但已标记为旧的结果',
      description: '说明系统保留了可用输出，但它不一定代表最新抓取批次。',
      nextAction: hasVisualReviewCandidates
        ? '如果本次目标是继续审核流程，可以先启动视觉复核；如果本次目标是拿最新数据，请重新抓取。'
        : '可以先导出当前结果做审计留档；如果必须拿最新结果，请重新抓取。',
    });
  } else if (result.cached) {
    guidance.push({
      key: 'cached',
      tone: 'success',
      label: '缓存结果',
      title: '当前结果来自最近一次成功缓存',
      description: '你现在看到的是已保存的可用结果，不需要重新抓取也能继续导出和复核。',
      nextAction: hasVisualReviewCandidates
        ? '下一步请直接启动视觉复核。'
        : (hasFinalReviewExport ? '如果视觉复核已经做完，下一步请直接导出最终复核表。' : '可先导出原始/测试/初筛结果继续核对。'),
    });
  } else {
    guidance.push({
      key: 'fresh',
      tone: 'success',
      label: scrapeRunning ? '运行中' : '已完成',
      title: scrapeRunning ? '当前流程仍在执行' : '当前显示的是本次抓取的新结果',
      description: scrapeRunning
        ? '页面会持续刷新状态；已返回的数据可以先看，但尚未代表最终全量结果。'
        : '这批结果已经完成初筛整理，可以直接进入后续审核与导出。',
      nextAction: hasVisualReviewCandidates
        ? '下一步请启动视觉复核。'
        : (hasFinalReviewExport ? '如果视觉复核已经做完，下一步请导出最终复核表。' : '可先导出原始/测试/初筛结果做交接。'),
    });
  }

  if (!result.is_partial && hasVisualReviewCandidates) {
    guidance.push({
      key: 'visual-next',
      tone: 'info',
      label: '下一步',
      title: '已有通过初筛且带封面的账号',
      description: `当前有 ${hasVisualReviewCandidates ? '可进入视觉复核的候选账号' : '候选账号'}，视觉复核会在现有初筛基础上补齐画面判断。`,
      nextAction: '下一步请点击“开始视觉复核”。',
    });
  }

  if (visualReviewCompleted || hasFinalReviewExport) {
    guidance.push({
      key: 'final-next',
      tone: 'success',
      label: '最终复核',
      title: hasInMemoryFinalReviewData
        ? '最终复核导出已就绪'
        : '后端已保存可复用的最终复核输入',
      description: hasInMemoryFinalReviewData
        ? '当前会话里的初筛结果和视觉复核结果都已齐备。'
        : '即使当前页面内存里的 `profile_reviews` 或 `visual_results` 不完整，后端也有可回退的保存结果。',
      nextAction: '下一步请直接导出最终复核表。',
    });
  }

  return guidance;
}

function normalizeVisualReviewSnapshot(review, fallbackKey = '') {
  if (!review || typeof review !== 'object') return null;

  const username = String(review.username || review.current_username || '').trim();
  const key = username || fallbackKey;
  if (!key) return null;

  const step = String(review.step || 'preparing').trim() || 'preparing';
  const decision = String(review.decision || '').trim();
  const reason = String(review.reason || '').trim();
  const requestedMode = String(review.requested_mode || '').trim();
  const recommendedMode = String(review.recommended_mode || '').trim();
  const appliedMode = String(review.applied_mode || '').trim();
  const downgradeReason = String(review.downgrade_reason || '').trim();
  const success = typeof review.success === 'boolean'
    ? review.success
    : !(step === 'failed' || step === 'collage_failed' || decision === 'Error');
  const rawPreviewUrls = Array.isArray(review.preview_urls)
    ? review.preview_urls
    : (Array.isArray(review.current_collage_urls) ? review.current_collage_urls : []);
  const rawReviewedPreviewUrls = Array.isArray(review.reviewed_collage_urls)
    ? review.reviewed_collage_urls
    : [];
  const previewUrls = rawPreviewUrls
    .map((item) => resolveBackendAssetUrl(item))
    .filter(Boolean);
  const previewUrl = resolveBackendAssetUrl(review.preview_url || review.current_collage_url);
  if (previewUrls.length === 0 && previewUrl) {
    previewUrls.push(previewUrl);
  }
  const reviewedPreviewUrls = rawReviewedPreviewUrls
    .map((item) => resolveBackendAssetUrl(item))
    .filter(Boolean);
  const reviewedCollageCount = typeof review.reviewed_collage_count === 'number'
    ? review.reviewed_collage_count
    : (reviewedPreviewUrls.length > 0 ? reviewedPreviewUrls.length : previewUrls.length);
  const normalizedReviewedPreviewUrls = reviewedPreviewUrls.length > 0
    ? reviewedPreviewUrls
    : previewUrls.slice(0, Math.max(0, reviewedCollageCount || previewUrls.length));

  return {
    key,
    username,
    previewUrl: normalizedReviewedPreviewUrls[0] || previewUrls[0] || previewUrl,
    previewUrls,
    reviewedPreviewUrls: normalizedReviewedPreviewUrls,
    collageCount: typeof review.collage_count === 'number'
      ? review.collage_count
      : previewUrls.length,
    reviewedCollageCount,
    unusedCollageCount: typeof review.unused_collage_count === 'number'
      ? review.unused_collage_count
      : Math.max(0, previewUrls.length - reviewedCollageCount),
    targetCollageCount: typeof review.target_collage_count === 'number'
      ? review.target_collage_count
      : null,
    requestedMode,
    recommendedMode,
    appliedMode,
    downgradeReason,
    collageErrorCount: typeof review.collage_error_count === 'number' ? review.collage_error_count : 0,
    coverCount: typeof review.cover_count === 'number' ? review.cover_count : null,
    requestedCoverCount: typeof review.requested_cover_count === 'number' ? review.requested_cover_count : null,
    failedCoverCount: typeof review.failed_cover_count === 'number' ? review.failed_cover_count : null,
    currentCoverIndex: typeof review.current_cover_index === 'number' ? review.current_cover_index : null,
    currentCoverTotal: typeof review.current_cover_total === 'number' ? review.current_cover_total : null,
    minRequiredCoverCount: typeof review.min_required_cover_count === 'number' ? review.min_required_cover_count : null,
    contractVersion: String(review.contract_version || ''),
    step,
    decision,
    reason,
    signals: Array.isArray(review.signals)
      ? review.signals.map((item) => String(item || '').trim()).filter(Boolean)
      : [],
    logLines: normalizeLiveReviewLogLines(review.log_lines),
    updatedAt: String(review.updated_at || ''),
    isCompleted: isVisualReviewFinalStep(step),
    isLive: Boolean(review.is_live),
    success,
    error: success ? '' : (String(review.error || '').trim() || reason),
  };
}

function normalizeVisualReviewHistory(historyItems) {
  if (!Array.isArray(historyItems)) return [];

  const items = [];
  historyItems.forEach((item, index) => {
    const normalized = normalizeVisualReviewSnapshot(item, `visual-history-${index}`);
    if (!normalized) return;

    const existingIndex = items.findIndex((entry) => entry.key === normalized.key);
    if (existingIndex >= 0) {
      items[existingIndex] = normalized;
      return;
    }
    items.push(normalized);
  });

  return items;
}

function getLiveReviewToneClassName(tone) {
  if (tone === 'success') {
    return 'border-emerald-200/80 bg-emerald-50/80 text-emerald-800';
  }
  if (tone === 'warning') {
    return 'border-amber-200/80 bg-amber-50/80 text-amber-800';
  }
  if (tone === 'error') {
    return 'border-rose-200/80 bg-rose-50/80 text-rose-800';
  }
  return 'border-gray-200/80 bg-white text-gray-700';
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

function formatJobStatus(status) {
  if (status === 'queued') return '排队中';
  if (status === 'running') return '运行中';
  if (status === 'cancelling') return '取消中';
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
    provider_start: '提交任务',
    provider_running: 'Apify 运行中',
    recovering_remote_run: '恢复远端运行',
    waiting_remote_run: '等待远端运行',
    downloading: '下载结果',
    filtering: '初筛中',
    batch_preparing: '准备批次',
    batch_completed: '批次完成',
    batch_failed: '批次失败',
    cancelling: '取消中',
    visual_reviewing: '视觉复核中',
    completed: '完成',
    failed: '失败',
    cancelled: '已取消',
  };
  return stageMap[stage] || stage || '未知';
}

function getJobProgressSnapshot(job) {
  const rawDone = typeof job?.progress?.done === 'number' ? job.progress.done : 0;
  const rawTotal = typeof job?.progress?.total === 'number' ? job.progress.total : null;
  const backendPercent = typeof job?.progress?.percent === 'number' ? job.progress.percent : null;
  const backendDeterminate = typeof job?.progress?.determinate === 'boolean' ? job.progress.determinate : null;

  if (backendDeterminate !== null) {
    return {
      done: rawDone,
      total: rawTotal,
      hasDeterminateProgress: backendDeterminate,
      progressPercent: backendDeterminate ? backendPercent : null,
    };
  }

  const stageProgressMap = {
    preparing: { done: 0, total: 4 },
    provider_start: { done: 1, total: 4 },
    provider_running: { done: 1, total: 4 },
    recovering_remote_run: { done: 2, total: 4 },
    waiting_remote_run: { done: 2, total: 4 },
    downloading: { done: 2, total: 4 },
    filtering: { done: 3, total: 4 },
    completed: { done: 4, total: 4 },
    failed: { done: 4, total: 4 },
    cancelling: { done: 4, total: 4 },
    cancelled: { done: 4, total: 4 },
  };

  if (typeof job?.batch_total === 'number' && job.batch_total > 0) {
    const total = job.batch_total;
    const batchIndex = typeof job.batch_index === 'number' ? job.batch_index : 0;
    const batchStageFractionMap = {
      batch_preparing: 0.08,
      provider_start: 0.18,
      provider_running: 0.45,
      recovering_remote_run: 0.55,
      waiting_remote_run: 0.6,
      downloading: 0.72,
      filtering: 0.9,
      batch_completed: 1,
      batch_failed: 1,
    };
    const inferredDone = job?.status === 'completed'
      ? total
      : job?.stage === 'batch_completed' || job?.stage === 'batch_failed'
        ? batchIndex
        : Math.max(0, batchIndex - 1);
    const done = Math.min(
      total,
      Math.max(rawTotal === total ? rawDone : 0, inferredDone),
    );
    const stageFraction = batchStageFractionMap[job?.stage] ?? (batchIndex > 0 ? 0.05 : 0);
    const effectiveDone = job?.status === 'completed'
      ? total
      : Math.min(
        total,
        Math.max(done, Math.max(0, batchIndex - 1) + stageFraction),
      );
    return {
      done,
      total,
      hasDeterminateProgress: true,
      progressPercent: total > 0
        ? Math.max(
          effectiveDone > 0 ? 5 : 0,
          Math.min(100, Math.round((effectiveDone / total) * 100)),
        )
        : null,
    };
  }

  if (rawTotal && rawTotal > 0) {
    const stageProgress = stageProgressMap[job?.stage];
    const done = stageProgress && stageProgress.total === rawTotal
      ? Math.max(rawDone, stageProgress.done)
      : rawDone;
    return {
      done,
      total: rawTotal,
      hasDeterminateProgress: true,
      progressPercent: Math.max(done > 0 ? 5 : 0, Math.min(100, Math.round((done / rawTotal) * 100))),
    };
  }

  const stageProgress = stageProgressMap[job?.stage];
  if (stageProgress) {
    return {
      done: stageProgress.done,
      total: stageProgress.total,
      hasDeterminateProgress: true,
      progressPercent: Math.max(stageProgress.done > 0 ? 5 : 0, Math.min(100, Math.round((stageProgress.done / stageProgress.total) * 100))),
    };
  }

  return {
    done: rawDone,
    total: rawTotal,
    hasDeterminateProgress: false,
    progressPercent: null,
  };
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

function formatCompactMetric(value) {
  if (value === null || value === undefined || value === '') return '';
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return String(value).trim();
  }
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(num);
}

function summarizeUploadText(text, maxLength = 140) {
  const normalized = String(text || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return '';
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength - 1)}…`;
}

function buildUploadMetadataHighlights(metadata) {
  if (!metadata || typeof metadata !== 'object') return [];

  const entries = [];
  const pushEntry = (label, value, formatter = null) => {
    const raw = value === null || value === undefined ? '' : value;
    const text = formatter ? formatter(raw) : String(raw).trim();
    if (!text) return;
    entries.push({ label, value: text });
  };

  pushEntry('地区', metadata.region);
  pushEntry('语言', metadata.language);
  pushEntry('邮箱', metadata.email);
  pushEntry('粉丝', metadata.followers, formatCompactMetric);
  pushEntry('均播', metadata.avg_views, formatCompactMetric);
  pushEntry('均赞', metadata.avg_likes, formatCompactMetric);
  pushEntry('最近发帖', metadata.last_post, (value) => String(value).trim().slice(0, 10));

  return entries;
}

function formatUploadFileSize(size) {
  const bytes = Number(size);
  if (!Number.isFinite(bytes) || bytes <= 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getWorkbookParsingStatus(percent) {
  if (percent < 74) {
    return {
      label: '文件已上传，正在读取工作簿...',
      badge: '解析中',
    };
  }

  if (percent < 88) {
    return {
      label: '正在识别平台与账号列...',
      badge: '识别中',
    };
  }

  if (percent < 97) {
    return {
      label: '正在校验数据并整理结果...',
      badge: '校验中',
    };
  }

  return {
    label: '正在写入结果，马上完成...',
    badge: '即将完成',
  };
}

function uploadWorkbookWithProgress(apiUrl, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let parsingTimer = null;

    const stopParsingProgress = () => {
      if (parsingTimer) {
        window.clearInterval(parsingTimer);
        parsingTimer = null;
      }
    };

    const startParsingProgress = () => {
      stopParsingProgress();
      let currentPercent = 60;

      const emitParsingProgress = () => {
        const status = getWorkbookParsingStatus(currentPercent);
        onProgress({
          phase: 'parsing',
          percent: currentPercent,
          label: status.label,
          badge: status.badge,
        });
      };

      emitParsingProgress();

      parsingTimer = window.setInterval(() => {
        currentPercent = Math.min(99, currentPercent + (currentPercent < 78 ? 3 : currentPercent < 92 ? 2 : 1));
        emitParsingProgress();
      }, 220);
    };

    xhr.open('POST', apiUrl, true);
    xhr.responseType = 'text';

    xhr.upload.addEventListener('loadstart', () => {
      onProgress({
        phase: 'uploading',
        percent: 6,
        label: '正在上传文件...',
      });
    });

    xhr.upload.addEventListener('progress', (event) => {
      if (!event.lengthComputable || !event.total) {
        onProgress({
          phase: 'uploading',
          percent: 18,
          label: '正在上传文件...',
        });
        return;
      }

      const rawPercent = Math.min(100, Math.round((event.loaded / event.total) * 100));
      const scaledPercent = Math.max(8, Math.min(55, Math.round(rawPercent * 0.55)));
      onProgress({
        phase: 'uploading',
        percent: scaledPercent,
        label: rawPercent >= 100 ? '文件已上传，正在解析工作簿...' : `正在上传文件 ${rawPercent}%`,
        badge: rawPercent >= 100 ? '处理中' : `${rawPercent}%`,
      });
    });

    xhr.upload.addEventListener('load', startParsingProgress);

    xhr.onload = () => {
      stopParsingProgress();

      let data = null;
      try {
        data = xhr.responseText ? JSON.parse(xhr.responseText) : {};
      } catch {
        reject(new Error('上传接口返回了无法识别的响应'));
        return;
      }

      if (xhr.status >= 200 && xhr.status < 300 && data?.success !== false) {
        resolve(data);
        return;
      }

      const detail = Array.isArray(data?.details) && data.details.length > 0
        ? ` ${data.details[0]}`
        : '';
      reject(new Error((data?.error || `上传失败（HTTP ${xhr.status}）`) + detail));
    };

    xhr.onerror = () => {
      stopParsingProgress();
      reject(new Error('上传请求失败，请检查后端服务是否可用'));
    };

    xhr.onabort = () => {
      stopParsingProgress();
      reject(new Error('上传已取消'));
    };

    xhr.send(formData);
  });
}

function formatTemplatePlatformLabel(platform) {
  return TEMPLATE_PLATFORM_LABELS[platform] || String(platform || '').trim() || 'Unknown';
}

function formatTemplateStatusLabel(status) {
  if (status === 'matched') return '已匹配';
  if (status === 'partial') return '部分匹配';
  if (status === 'missing_capabilities') return '能力缺口';
  if (status === 'ambiguous') return '解析歧义';
  if (status === 'unsupported') return '当前不支持';
  if (status === 'blocked_sensitive_attribute') return '敏感属性禁用';
  return status || '未标记';
}

function getTemplateStatusClassName(status) {
  if (status === 'matched') {
    return 'border-emerald-200/80 bg-emerald-50/90 text-emerald-700';
  }
  if (status === 'partial') {
    return 'border-amber-200/80 bg-amber-50/90 text-amber-700';
  }
  if (status === 'missing_capabilities') {
    return 'border-orange-200/80 bg-orange-50/90 text-orange-700';
  }
  if (status === 'ambiguous') {
    return 'border-sky-200/80 bg-sky-50/90 text-sky-700';
  }
  if (status === 'unsupported') {
    return 'border-rose-200/80 bg-rose-50/90 text-rose-700';
  }
  if (status === 'blocked_sensitive_attribute') {
    return 'border-slate-200/80 bg-slate-100/90 text-slate-700';
  }
  return 'border-gray-200/80 bg-gray-50/90 text-gray-700';
}

function getProfileReviewKey(item, fallbackIndex) {
  const firstCover = Array.isArray(item?.covers) && item.covers.length > 0
    ? String(item.covers[0] || '').trim()
    : '';
  const parts = [
    String(item?.username || '').trim(),
    String(item?.profile_url || '').trim(),
    firstCover,
  ].filter(Boolean);

  if (parts.length > 0) {
    return parts.join('::');
  }
  return `unknown-${fallbackIndex}`;
}

function App() {
  const [activeTab, setActiveTab] = useState('tiktok');
  const [submitting, setSubmitting] = useState(false);
  const [scrapeRunning, setScrapeRunning] = useState(false);
  const [visualLoading, setVisualLoading] = useState(false);
  const [finalReviewDownloading, setFinalReviewDownloading] = useState(false);
  const [scrapeJob, setScrapeJob] = useState(null);
  const [visualJob, setVisualJob] = useState(null);
  const [scrapeAbortController, setScrapeAbortController] = useState(null);
  const [visualAbortController, setVisualAbortController] = useState(null);
  const [result, setResult] = useState(null);
  const [resultPlatform, setResultPlatform] = useState(null);
  const [error, setError] = useState(null);
  const [visualError, setVisualError] = useState(null);
  const [tableData, setTableData] = useState([]);
  const [visualResults, setVisualResults] = useState({});
  const [visualProgress, setVisualProgress] = useState({ done: 0, total: 0 });
  const [liveVisualReview, setLiveVisualReview] = useState(null);
  const [visualReviewHistory, setVisualReviewHistory] = useState([]);
  const [visualReviewSelection, setVisualReviewSelection] = useState({ mode: 'live', key: null });
  const [visualPreviewModal, setVisualPreviewModal] = useState(null);
  const [visualReviewMode, setVisualReviewMode] = useState(VISUAL_REVIEW_MODE_AUTO);
  const [expandedCards, setExpandedCards] = useState(() => new Set());
  const [activeWorkspace, setActiveWorkspace] = useState('run');
  const [activeResultTab, setActiveResultTab] = useState('overview');
  const [showTemplateWorkbench, setShowTemplateWorkbench] = useState(false);
  const [templateInput, setTemplateInput] = useState('');
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateError, setTemplateError] = useState(null);
  const [templateResult, setTemplateResult] = useState(null);
  const [templatePlatform, setTemplatePlatform] = useState('tiktok');

  // Form states
  const [tiktokProfiles, setTiktokProfiles] = useState('');
  const [tiktokLimit, setTiktokLimit] = useState(20);
  const [tiktokOptions, setTiktokOptions] = useState({
    downloadVideos: false,
    downloadCovers: true,
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
  const [uploadResult, setUploadResult] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);

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
    setVisualLoading(false);
    setVisualResults({});
    setVisualProgress({ done: 0, total: 0 });
    setVisualJob(null);
    setLiveVisualReview(null);
    setVisualReviewHistory([]);
    setVisualReviewSelection({ mode: 'live', key: null });
    setVisualPreviewModal(null);
    setExpandedCards(new Set());
    setActiveWorkspace('run');
    setActiveResultTab('overview');
    setShowTemplateWorkbench(false);
  }, [activeTab]);

  useEffect(() => {
    if (!result) {
      setActiveWorkspace('run');
      setActiveResultTab('overview');
    }
  }, [result]);

  useEffect(() => () => {
    scrapeAbortController?.abort();
    visualAbortController?.abort();
  }, [scrapeAbortController, visualAbortController]);

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

  const clearVisualReviewState = () => {
    setVisualLoading(false);
    setVisualResults({});
    setVisualProgress({ done: 0, total: 0 });
    setLiveVisualReview(null);
    setVisualReviewHistory([]);
    setVisualReviewSelection({ mode: 'live', key: null });
    setVisualPreviewModal(null);
    setVisualJob(null);
  };

  const syncVisualReviewHistory = (historyItems) => {
    const normalizedHistory = normalizeVisualReviewHistory(historyItems);
    const previousLastItem = visualReviewHistory[visualReviewHistory.length - 1];
    const nextLastItem = normalizedHistory[normalizedHistory.length - 1];
    const hasNewHistoryItem = normalizedHistory.length > visualReviewHistory.length
      || (nextLastItem?.key && nextLastItem.key !== previousLastItem?.key);

    setVisualReviewHistory(normalizedHistory);

    if (normalizedHistory.length === 0) {
      return;
    }

    setVisualReviewSelection((currentSelection) => {
      if (currentSelection.mode === 'live' && hasNewHistoryItem) {
        return { mode: 'history', key: nextLastItem.key };
      }

      if (normalizedHistory.some((item) => item.key === currentSelection.key)) {
        return currentSelection;
      }

      return { mode: 'history', key: nextLastItem.key };
    });
  };

  const selectVisualReviewHistoryByIndex = (index) => {
    setVisualReviewSelection(() => {
      const targetItem = visualReviewHistory[index];
      if (!targetItem) {
        return { mode: 'history', key: null };
      }
      return { mode: 'history', key: targetItem.key };
    });
  };

  const handleReturnToLiveReview = () => {
    setVisualReviewSelection({ mode: 'live', key: null });
  };

  const handleFileUpload = async (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    setUploading(true);
    setError(null);
    setUploadProgress({
      phase: 'uploading',
      percent: 6,
      label: '正在上传文件...',
      badge: '准备中',
      fileName: selectedFile.name,
      fileSize: selectedFile.size,
    });
    try {
      const data = await uploadWorkbookWithProgress(`${API_BASE}/upload`, formData, (progress) => {
        setUploadProgress((current) => ({
          phase: progress.phase || current?.phase || 'uploading',
          percent: typeof progress.percent === 'number' ? progress.percent : (current?.percent || 0),
          label: progress.label || current?.label || '正在处理文件...',
          badge: progress.badge || current?.badge || null,
          fileName: selectedFile.name,
          fileSize: selectedFile.size,
        }));
      });

      if (data.success) {
        const tiktokList = Array.isArray(data?.grouped_data?.tiktok)
          ? data.grouped_data.tiktok.map((u) => {
              try {
                const url = new URL(u);
                const pathParts = url.pathname.split('/');
                const userPart = pathParts.find((p) => p.startsWith('@'));
                return userPart ? userPart.substring(1) : u;
              } catch {
                return u;
              }
            })
          : [];
        const instaList = Array.isArray(data?.grouped_data?.instagram)
          ? data.grouped_data.instagram.map((u) => {
              try {
                const url = new URL(u);
                const pathParts = url.pathname.split('/').filter(Boolean);
                return pathParts.length > 0 ? pathParts[0] : u;
              } catch {
                return u;
              }
            })
          : [];
        const youtubeList = Array.isArray(data?.grouped_data?.youtube)
          ? data.grouped_data.youtube
          : [];

        setUploadResult(data);
        setUploadProgress(null);

        setFullTiktokProfiles(tiktokList);
        setFullInstagramUsernames(instaList);
        setFullYoutubeQueries(youtubeList);

        if (youtubeList.length > 0) {
          setYoutubeMode('channel');
        }
      } else {
        setError(data.error);
        setUploadProgress({
          phase: 'failed',
          percent: 100,
          label: '上传失败，请检查模板内容后重试。',
          badge: '失败',
          fileName: selectedFile.name,
          fileSize: selectedFile.size,
        });
      }
    } catch (err) {
      setError(err.message);
      setUploadProgress({
        phase: 'failed',
        percent: 100,
        label: '上传失败，请检查模板或服务状态。',
        badge: '失败',
        fileName: selectedFile.name,
        fileSize: selectedFile.size,
      });
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const handleScrape = async () => {
    if (scrapeRunning || submitting) {
      return;
    }

    const requestedPlatform = activeTab;
    const controller = new AbortController();
    let lastPartialSignature = '';

    setActiveWorkspace('run');
    setActiveResultTab('overview');
    setShowTemplateWorkbench(false);
    setSubmitting(true);
    setScrapeRunning(true);
    setScrapeAbortController(controller);
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
          clearVisualReviewState();
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
        clearVisualReviewState();
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
      setScrapeAbortController((currentController) => (
        currentController === controller ? null : currentController
      ));
    }
  };

  const handleCancelScrape = async () => {
    const currentJobId = scrapeJob?.id;
    const currentController = scrapeAbortController;

    if (!currentJobId) {
      currentController?.abort();
      setScrapeAbortController(null);
      setSubmitting(false);
      setScrapeRunning(false);
      setScrapeJob((currentJob) => currentJob ? {
        ...currentJob,
        status: 'cancelled',
        stage: 'cancelled',
        message: '已取消提交'
      } : currentJob);
      return;
    }

    try {
      currentController?.abort();
      setScrapeAbortController(null);
      setSubmitting(false);
      setScrapeRunning(false);
      setScrapeJob((currentJob) => currentJob ? {
        ...currentJob,
        status: 'cancelling',
        stage: 'cancelling',
        message: '正在请求取消'
      } : currentJob);

      const response = await fetch(`${API_BASE}/jobs/${currentJobId}/cancel`, {
        method: 'POST'
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || '取消采集失败');
      }
      if (data.job) {
        setScrapeJob(data.job);
      }

      const finalJob = await pollJobUntilDone(currentJobId, (job) => {
        setScrapeJob(job);
      });
      if (finalJob) {
        setScrapeJob(finalJob);
      }
    } catch (err) {
      setScrapeJob((currentJob) => currentJob ? {
        ...currentJob,
        status: currentJob.status === 'cancelling' ? 'cancelling' : 'cancelled',
        stage: currentJob.stage === 'cancelling' ? 'cancelling' : 'cancelled',
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
      if (!response.ok || !Array.isArray(data)) {
        setTableData([]);
        console.error('Unexpected results payload', data);
        return;
      }
      setTableData(data);
    } catch (err) {
      setTableData([]);
      console.error("Failed to fetch results", err);
    }
  };

  const handleGenerateTemplates = async () => {
    const trimmedInput = String(templateInput || '').trim();
    setShowTemplateWorkbench(true);
    if (!trimmedInput) {
      setTemplateError('请输入一段审核需求，再编译 RuleSpec。');
      return;
    }

    setTemplateLoading(true);
    setTemplateError(null);

    try {
      const response = await fetch(`${API_BASE}/rulespec/compile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sop_text: trimmedInput,
          persist: true,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || 'RuleSpec 编译失败');
      }

      setTemplateResult(data);
      setTemplatePlatform((currentPlatform) => {
        if (data?.field_match_report?.platforms?.[currentPlatform]) {
          return currentPlatform;
        }
        if (data?.field_match_report?.platforms?.[activeTab]) {
          return activeTab;
        }
        return 'tiktok';
      });
    } catch (err) {
      setTemplateError(err.message || 'RuleSpec 编译失败');
    } finally {
      setTemplateLoading(false);
    }
  };

  const downloadFile = (format) => {
    const platform = resultPlatform || activeTab;
    window.location.href = `${API_BASE}/download/${platform}/${format}`;
  };

  const downloadPrescreenReview = () => {
    const platform = resultPlatform || activeTab;
    window.location.href = `${API_BASE}/download/${platform}/prescreen-review`;
  };

  const downloadImageReview = () => {
    const platform = resultPlatform || activeTab;
    window.location.href = `${API_BASE}/download/${platform}/image-review`;
  };

  const downloadTestInfo = () => {
    const platform = resultPlatform || activeTab;
    window.location.href = `${API_BASE}/download/${platform}/test-info`;
  };

  const downloadTestInfoJson = () => {
    const platform = resultPlatform || activeTab;
    window.location.href = `${API_BASE}/download/${platform}/test-info-json`;
  };

  const downloadFinalReview = async () => {
    const platform = resultPlatform || activeTab;
    const savedArtifactsAvailable = Boolean(result?.saved_final_review_artifacts_available);
    if (!savedArtifactsAvailable && (resultProfileReviews.length === 0 || Object.keys(visualResults).length === 0)) {
      setVisualError('暂无可导出的最终复核结果。');
      return;
    }

    setFinalReviewDownloading(true);
    setVisualError(null);

    try {
      const response = await fetch(`${API_BASE}/download/${platform}/final-review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_reviews: resultProfileReviews,
          visual_results: visualResults,
        }),
      });

      if (!response.ok) {
        let message = '最终复核表导出失败';
        try {
          const data = await response.json();
          if (data?.error) {
            message = data.error;
          }
        } catch {
          // Ignore JSON parse errors and use the fallback message.
        }
        throw new Error(message);
      }

      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `${platform}_final_review.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
    } catch (err) {
      setVisualError(err.message || '最终复核表导出失败');
    } finally {
      setFinalReviewDownloading(false);
    }
  };

  const handleVisualReview = async () => {
    const candidates = (result?.profile_reviews || []).filter(
      (item) => item.status === 'Pass' && Array.isArray(item.covers) && item.covers.length > 0
    );

    if (candidates.length === 0) {
      setVisualError('当前没有可进行视觉复核的博主。');
      return;
    }

    const controller = new AbortController();
    setActiveWorkspace('results');
    setActiveResultTab('visual-review');
    setVisualLoading(true);
    setVisualError(null);
    setVisualResults({});
    setVisualProgress({ done: 0, total: candidates.length });
    setLiveVisualReview(null);
    setVisualReviewHistory([]);
    setVisualReviewSelection({ mode: 'live', key: null });
    setVisualPreviewModal(null);
    setVisualJob(null);
    setVisualAbortController(controller);

    try {
      const response = await fetch(`${API_BASE}/jobs/visual-review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          platform: activeTab,
          reviewMode: visualReviewMode,
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
        if (job?.partial_result?.visual_results) {
          setVisualResults(job.partial_result.visual_results);
        }
        if (job?.partial_result?.live_review) {
          setLiveVisualReview(job.partial_result.live_review);
        }
        if (Array.isArray(job?.partial_result?.review_history)) {
          syncVisualReviewHistory(job.partial_result.review_history);
        }
      }, controller.signal);

      if (!finalJob || finalJob.status === 'cancelled') {
        return;
      }

      if (finalJob.status === 'completed') {
        setVisualJob(finalJob);
        setVisualResults(finalJob.result?.visual_results || {});
        setLiveVisualReview(finalJob.result?.live_review || finalJob.partial_result?.live_review || null);
        syncVisualReviewHistory(finalJob.result?.review_history || finalJob.partial_result?.review_history || []);
      } else {
        throw new Error(finalJob.error || '视觉复核失败');
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        return;
      }
      setVisualError(err.message);
    } finally {
      setVisualLoading(false);
      setVisualAbortController((currentController) => (
        currentController === controller ? null : currentController
      ));
    }
  };

  const renderJobCard = (title, job, tone = 'info') => {
    if (!job) return null;

    const palette = tone === 'warning'
      ? {
        icon: 'bg-amber-100 text-amber-700',
        progress: 'bg-amber-400',
        chip: 'border-amber-200/80 bg-amber-50/80 text-amber-800',
      }
      : {
        icon: 'bg-sky-100 text-sky-700',
        progress: 'bg-sky-500',
        chip: 'border-sky-200/80 bg-sky-50/80 text-sky-800',
      };
    
    const {
      done,
      total,
      hasDeterminateProgress,
      progressPercent,
    } = getJobProgressSnapshot(job);
    const progressText = hasDeterminateProgress
      ? (typeof progressPercent === 'number' && total === 100 ? `${progressPercent}%` : `${done} / ${total}`)
      : '等待回传';
    const targetPreview = formatTargetPreview(job);

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        whileHover={{ y: -2 }}
        transition={hoverLiftTransition}
        className="rounded-[24px] border border-gray-200/70 bg-white/95 p-5 shadow-[0_1px_3px_rgba(15,23,42,0.04),0_16px_40px_rgba(15,23,42,0.04)] backdrop-blur"
      >
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${palette.icon}`}>
              {tone === 'warning' ? <AlertCircle className="w-5 h-5" /> : <RefreshCw className={`w-5 h-5 ${job.status === 'running' || job.status === 'cancelling' ? 'animate-spin' : ''}`} />}
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-base font-semibold text-gray-900">{title}</h3>
                <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-600">
                  {formatJobStatus(job.status)} / {formatJobStage(job.stage)}
                </span>
              </div>
              <p className="mt-1 truncate text-sm text-gray-500">{job.message || '任务进行中'}</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 xl:max-w-[52%] xl:justify-end">
            <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium ${palette.chip}`}>
              进度 {progressText}
            </span>
            {typeof job.batch_index === 'number' && typeof job.batch_total === 'number' && (
              <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700">
                批次 {job.batch_index} / {job.batch_total}
              </span>
            )}
            {(job.current_username || targetPreview) && (
              <span className="inline-flex max-w-full items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700">
                <span className="mr-1.5 text-gray-400">当前</span>
                <span className="max-w-[180px] truncate text-gray-900">{job.current_username || targetPreview}</span>
              </span>
            )}
            {(typeof job.passed_count === 'number' || typeof job.rejected_count === 'number' || typeof job.failed_count === 'number') && (
              <>
                <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">
                  通过 {job.passed_count || 0}
                </span>
                <span className="inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700">
                  拒绝 {job.rejected_count || 0}
                </span>
                <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium ${palette.chip}`}>
                  失败 {job.failed_count || 0}
                </span>
              </>
            )}
          </div>
        </div>

        <div className="mt-4 h-2.5 w-full overflow-hidden rounded-full bg-gray-100">
          {hasDeterminateProgress ? (
            <motion.div 
              className={`h-full ${palette.progress}`} 
              initial={{ width: 0 }}
              animate={{ width: `${progressPercent}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
            />
          ) : (
            <motion.div 
              className={`h-full w-1/3 ${palette.progress}`} 
              animate={{ x: ["-100%", "300%"] }}
              transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
            />
          )}
        </div>
      </motion.div>
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
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        whileHover={{ y: -2 }}
        transition={hoverLiftTransition}
        className="rounded-[24px] border border-gray-200/70 bg-[#FCFCFC] p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04),0_16px_40px_rgba(15,23,42,0.04)] md:p-7"
      >
        <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            {result?.is_partial ? <Clock className="w-5 h-5 text-blue-500" /> : <CheckCircle className="w-5 h-5 text-green-500" />}
            {result?.is_partial ? '当前进度' : '筛选统计'}
          </h3>
          <div className="flex flex-wrap gap-4 rounded-2xl border border-gray-200/70 bg-white px-4 py-3 text-sm font-medium text-gray-600 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
            <span>总计 <strong className="text-gray-900">{result?.is_partial ? `${profileReviews.length} / ${requestedTotal}` : requestedTotal}</strong></span>
            <span className="text-green-600">通过 {passedCount}</span>
            <span className="text-red-600">拒绝 {rejectedCount}</span>
          </div>
        </div>

        <div className="grid gap-4">
          <AnimatePresence>
            {sortedReviews.map((item, index) => {
              const cardKey = getProfileReviewKey(item, index);
              const expanded = expandedCards.has(cardKey);
              const tone = getProfileCardTone(item.status, item.soft_flags);
              const matchedFailedBatch = findFailedBatchForProfile(item, resultFailedBatches);
              const failedBatchReason = formatFailedBatchReason(matchedFailedBatch);
              const fullReason = formatReviewReason(item.reason);
              const summaryReason = formatReasonSummary(item);
              const showExpansion = needsExpansion(item);
              const displayReason = expanded || !showExpansion ? fullReason : summaryReason;
              const softFlagsText = Array.isArray(item.soft_flags)
                ? item.soft_flags.map((flag) => formatSoftFlag(flag)).filter(Boolean)
                : [];
              const uploadMetadata = item?.upload_metadata && typeof item.upload_metadata === 'object'
                ? item.upload_metadata
                : null;
              const uploadNickname = String(uploadMetadata?.nickname || '').trim();
              const uploadHandle = String(uploadMetadata?.handle || '').trim().replace(/^@+/, '');
              const currentUsername = String(item?.username || '').trim().replace(/^@+/, '');
              const showUploadHandle = Boolean(uploadHandle) && uploadHandle.toLowerCase() !== currentUsername.toLowerCase();
              const uploadDescription = summarizeUploadText(uploadMetadata?.description || '');
              const uploadHighlights = buildUploadMetadataHighlights(uploadMetadata);
              const shouldShowUploadMeta = Boolean(uploadNickname || showUploadHandle || uploadDescription || uploadHighlights.length > 0);

              let borderAccent = 'border-l-gray-300';
              if (item.status === 'Pass') borderAccent = 'border-l-green-500';
              if (item.status === 'Reject') borderAccent = 'border-l-red-500';
              if (item.status === 'Pass' && softFlagsText.length > 0) borderAccent = 'border-l-amber-500';

              return (
                <motion.div
                  layout
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  whileHover={{ y: -1.5 }}
                  key={cardKey}
                  className={`group relative border ${borderAccent} border-l-[6px] border-y-gray-200/70 border-r-gray-200/70 rounded-[22px] p-5 bg-white shadow-[0_1px_3px_rgba(15,23,42,0.04)] transition-[box-shadow,border-color] duration-300 hover:border-gray-300/80 hover:shadow-[0_10px_24px_rgba(15,23,42,0.07)]`}
                >
                  <div className="flex justify-between items-start gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <strong className="text-base font-semibold text-gray-900 flex items-center gap-1.5">
                          {tone.icon} {item.username || '未知账号'}
                        </strong>
                        <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                          item.status === 'Pass' ? 'bg-green-100 text-green-800' :
                          item.status === 'Reject' ? 'bg-red-100 text-red-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {tone.label}
                        </span>
                        {softFlagsText.map((flagText) => (
                          <span key={`${cardKey}-${flagText}`} className="bg-amber-100 text-amber-800 px-2.5 py-0.5 rounded-full text-xs font-medium">
                            {flagText}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0 rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600">
                      <ImageIcon className="w-3.5 h-3.5 opacity-70" />
                      <span>封面 {item.covers?.length || 0}</span>
                    </div>
                  </div>

                  {shouldShowUploadMeta && (
                    <div className="mt-3 space-y-3">
                      {(uploadNickname || showUploadHandle) && (
                        <div className="flex flex-wrap items-center gap-2 text-sm text-gray-500">
                          {uploadNickname && (
                            <span className="font-medium text-gray-700">{uploadNickname}</span>
                          )}
                          {showUploadHandle && (
                            <span className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5 text-xs font-medium text-gray-600">
                              @{uploadHandle}
                            </span>
                          )}
                        </div>
                      )}

                      {uploadHighlights.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {uploadHighlights.map((entry) => (
                            <span
                              key={`${cardKey}-${entry.label}-${entry.value}`}
                              className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-medium text-gray-600"
                            >
                              <span className="text-gray-400">{entry.label}</span>
                              <span className="ml-1 text-gray-700">{entry.value}</span>
                            </span>
                          ))}
                        </div>
                      )}

                      {uploadDescription && (
                        <div className="rounded-2xl border border-gray-200/70 bg-gray-50/70 px-4 py-3 text-sm text-gray-600 leading-relaxed">
                          {uploadDescription}
                        </div>
                      )}
                    </div>
                  )}

                  {displayReason && (
                    <motion.div layout className="mt-3 text-sm text-gray-600 leading-relaxed">
                      <span>{displayReason}</span>
                      {showExpansion && (
                        <button
                          onClick={() => toggleCardExpansion(cardKey)}
                          className="ml-2 inline-flex cursor-pointer items-center gap-0.5 font-medium text-gray-900 transition-colors hover:text-gray-600 focus:outline-none"
                        >
                          {expanded ? (
                            <><ChevronUp className="w-3.5 h-3.5" /> 收起</>
                          ) : (
                            <><ChevronDown className="w-3.5 h-3.5" /> 展开</>
                          )}
                        </button>
                      )}
                    </motion.div>
                  )}

                  {failedBatchReason && (
                    <div className="mt-3 rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-sm leading-relaxed text-amber-900">
                      {failedBatchReason}
                    </div>
                  )}

                  <div className="mt-4 flex items-center text-sm">
                    {item.profile_url ? (
                      <a 
                        href={item.profile_url} 
                        target="_blank" 
                        rel="noreferrer" 
                        className="inline-flex items-center gap-1.5 font-medium text-gray-900 transition-colors hover:text-gray-600 hover:underline"
                      >
                        <LinkIcon className="w-3.5 h-3.5" />
                        {formatShortProfileUrl(item.profile_url)}
                      </a>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-gray-400">
                        <LinkIcon className="w-3.5 h-3.5" /> 无链接
                      </span>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      </motion.div>
    );
  };

  const resultProfileReviews = Array.isArray(result?.profile_reviews) ? result.profile_reviews : [];
  const visualReviewCandidates = resultProfileReviews.filter(
    (item) => item.status === 'Pass' && Array.isArray(item.covers) && item.covers.length > 0
  );
  const resultRequestedTotal = result?.requested_total || result?.filter_stats?.original_profiles || resultProfileReviews.length;
  const resultPassedCount = resultProfileReviews.filter((item) => item.status === 'Pass').length;
  const resultRejectedCount = resultProfileReviews.filter((item) => item.status !== 'Pass').length;
  const rawRecordCount = Array.isArray(tableData) ? tableData.length : 0;
  const hasVisualReviewCandidates = !result?.is_partial && visualReviewCandidates.length > 0;
  const visualReviewRecommendation = summarizeVisualReviewRecommendation(visualReviewCandidates);
  const savedFinalReviewArtifactsAvailable = Boolean(result?.saved_final_review_artifacts_available);
  const hasInMemoryFinalReviewData = resultProfileReviews.length > 0 && Object.keys(visualResults).length > 0;
  const visualReviewCompleted = visualJob?.status === 'completed' || Object.keys(visualResults).length > 0;
  const hasFinalReviewExport = hasInMemoryFinalReviewData || savedFinalReviewArtifactsAvailable;
  const resultStateGuidance = buildResultStateGuidance({
    scrapeRunning,
    result,
    hasVisualReviewCandidates,
    visualReviewCompleted,
    hasFinalReviewExport,
    hasInMemoryFinalReviewData,
    savedFinalReviewArtifactsAvailable,
  });
  const exportActionGroups = [
    {
      key: 'raw-debug',
      eyebrow: '原始与调试导出',
      title: '保留原始路由与调试别名',
      description: '原始 JSON / Excel 仍然是 raw 下载；测试信息导出用于调试与审计交叉核对。',
      actions: [
        {
          key: 'raw-json',
          label: '原始采集 JSON',
          hint: '真实 raw 路由：/api/download/<platform>/json',
          onClick: () => downloadFile('json'),
          enabled: true,
        },
        {
          key: 'raw-excel',
          label: '原始采集 Excel',
          hint: '真实 raw 路由：/api/download/<platform>/excel',
          onClick: () => downloadFile('excel'),
          enabled: true,
        },
        {
          key: 'test-info',
          label: '测试信息 Excel',
          hint: '账号审核摘要 + 原始数据 sheet，供排查与 spot check',
          onClick: downloadTestInfo,
          enabled: true,
        },
        {
          key: 'test-info-json',
          label: '测试信息 JSON（调试别名）',
          hint: '这不是 raw JSON；实际走 /api/download/<platform>/test-info-json',
          onClick: downloadTestInfoJson,
          enabled: true,
        },
      ],
    },
    {
      key: 'review-handoff',
      eyebrow: '复核与交接导出',
      title: '按流程阶段继续交接',
      description: '初筛、带封面复核、最终复核都保留在同一屏，当前可用性直接反映后端真实状态。',
      actions: [
        {
          key: 'prescreen-review',
          label: '初筛复核 Excel',
          hint: resultProfileReviews.length > 0 ? '规则层交接表，适合先做人审对账' : '等待初筛结果返回后可导出',
          onClick: downloadPrescreenReview,
          enabled: resultProfileReviews.length > 0,
        },
        {
          key: 'image-review',
          label: 'image-review Excel',
          hint: resultProfileReviews.length > 0 ? '带封面初筛表，便于进入画面核对' : '等待至少一批带封面的初筛结果',
          onClick: downloadImageReview,
          enabled: resultProfileReviews.length > 0,
        },
        {
          key: 'final-review',
          label: finalReviewDownloading ? '导出最终复核表...' : 'final-review Excel',
          hint: hasInMemoryFinalReviewData
            ? '当前会话已具备完整初筛 + 视觉复核输入'
            : savedFinalReviewArtifactsAvailable
              ? '当前将回退到后端已保存 artifact，无需依赖当前页面内存'
              : '等待视觉复核完成或后端保存 artifact 可用',
          onClick: downloadFinalReview,
          enabled: hasFinalReviewExport && !finalReviewDownloading,
          busy: finalReviewDownloading,
        },
      ],
    },
  ];
  const activeResultPlatform = (resultPlatform || activeTab).toUpperCase();
  const resultTabOptions = [
    { key: 'overview', label: '概览' },
    { key: 'profiles', label: '博主卡片' },
    { key: 'visual-review', label: '视觉复核' },
    { key: 'export-handoff', label: '导出交接' },
  ];
  const activeResultTabLabel = resultTabOptions.find((item) => item.key === activeResultTab)?.label || '概览';
  const showingPreviousResultWhileRunning = Boolean(scrapeRunning && result && !result.is_partial);
  const resultWorkspaceStatus = result?.is_partial
    ? '增量结果'
    : showingPreviousResultWhileRunning
      ? '采集中（沿用上次结果）'
      : result?.used_fallback
      ? '回退快照'
      : result?.stale_result
        ? '旧结果'
        : result?.cached
          ? '缓存结果'
          : '最新完成结果';
  const resultFailedBatches = Array.isArray(result?.failed_batches) ? result.failed_batches : [];
  const failedBatchSummary = buildFailedBatchSummary(resultFailedBatches);
  const resultBannerMessage = showingPreviousResultWhileRunning
    ? (scrapeJob?.message || '正在等待本次任务返回首批结果。')
    : result?.message;
  const resultBannerToneClassName = showingPreviousResultWhileRunning
    ? 'text-sky-700'
    : (result?.cached ? 'text-amber-700' : 'text-emerald-700');
  const parsedTemplateSteps = Array.isArray(templateResult?.parsed_sop?.steps) ? templateResult.parsed_sop.steps : [];
  const availableTemplatePlatforms = ['tiktok', 'instagram', 'youtube'].filter(
    (platform) => templateResult?.field_match_report?.platforms?.[platform],
  );
  const selectedTemplate = templateResult?.field_match_report?.platforms?.[templatePlatform] || null;
  const selectedTemplateChecks = (Array.isArray(selectedTemplate?.rule_matches) ? selectedTemplate.rule_matches : []).filter(
    (item) => item?.status !== 'blocked_sensitive_attribute',
  );
  const selectedTemplateGaps = selectedTemplateChecks.filter((item) => (
    item?.status === 'partial'
    || item?.status === 'missing_capabilities'
    || item?.status === 'ambiguous'
    || item?.status === 'unsupported'
  ));
  const selectedTemplateBlockedRules = (Array.isArray(selectedTemplate?.rule_matches) ? selectedTemplate.rule_matches : []).filter(
    (item) => item?.status === 'blocked_sensitive_attribute',
  );
  const activeLiveReview = liveVisualReview || visualJob?.partial_result?.live_review || visualJob?.result?.live_review || null;
  const activeLiveReviewSnapshot = normalizeVisualReviewSnapshot(
    activeLiveReview ? { ...activeLiveReview, is_live: true } : null,
    'visual-live',
  );
  const latestVisualReviewHistory = visualReviewHistory[visualReviewHistory.length - 1] || null;
  const selectedVisualReviewIndex = visualReviewHistory.findIndex((item) => item.key === visualReviewSelection.key);
  const selectedVisualReviewHistory = selectedVisualReviewIndex >= 0
    ? visualReviewHistory[selectedVisualReviewIndex]
    : null;
  const effectiveSelectedVisualReview = visualReviewSelection.mode === 'history'
    ? (selectedVisualReviewHistory || latestVisualReviewHistory || activeLiveReviewSnapshot)
    : (activeLiveReviewSnapshot || latestVisualReviewHistory);
  const effectiveSelectedHistoryIndex = visualReviewSelection.mode === 'history'
    ? (selectedVisualReviewIndex >= 0 ? selectedVisualReviewIndex : visualReviewHistory.length - 1)
    : -1;
  const effectiveVisualReviewLogs = effectiveSelectedVisualReview?.logLines || [];
  const effectiveVisualReviewPreviewUrls = Array.isArray(effectiveSelectedVisualReview?.previewUrls)
    ? effectiveSelectedVisualReview.previewUrls
    : [];
  const effectiveVisualReviewedPreviewUrls = Array.isArray(effectiveSelectedVisualReview?.reviewedPreviewUrls)
    ? effectiveSelectedVisualReview.reviewedPreviewUrls
    : [];
  const effectiveVisualReviewCollageUrl = effectiveVisualReviewedPreviewUrls[0]
    || effectiveVisualReviewPreviewUrls[0]
    || effectiveSelectedVisualReview?.previewUrl
    || '';
  const effectiveVisualReviewCollageCount = typeof effectiveSelectedVisualReview?.collageCount === 'number'
    ? effectiveSelectedVisualReview.collageCount
    : effectiveVisualReviewPreviewUrls.length;
  const effectiveVisualReviewedCollageCount = typeof effectiveSelectedVisualReview?.reviewedCollageCount === 'number'
    ? effectiveSelectedVisualReview.reviewedCollageCount
    : effectiveVisualReviewedPreviewUrls.length;
  const effectiveVisualUnusedCollageCount = typeof effectiveSelectedVisualReview?.unusedCollageCount === 'number'
    ? effectiveSelectedVisualReview.unusedCollageCount
    : Math.max(0, effectiveVisualReviewCollageCount - effectiveVisualReviewedCollageCount);
  const effectiveVisualCollageErrorCount = typeof effectiveSelectedVisualReview?.collageErrorCount === 'number'
    ? effectiveSelectedVisualReview.collageErrorCount
    : 0;
  const effectiveVisualReviewTargetCollageCount = typeof effectiveSelectedVisualReview?.targetCollageCount === 'number'
    ? effectiveSelectedVisualReview.targetCollageCount
    : null;
  const effectiveVisualRequestedMode = effectiveSelectedVisualReview?.requestedMode || '';
  const effectiveVisualRecommendedMode = effectiveSelectedVisualReview?.recommendedMode || '';
  const effectiveVisualAppliedMode = effectiveSelectedVisualReview?.appliedMode || '';
  const effectiveVisualDowngradeReason = effectiveSelectedVisualReview?.downgradeReason || '';
  const effectiveVisualCoverLoadedCount = typeof effectiveSelectedVisualReview?.coverCount === 'number'
    ? effectiveSelectedVisualReview.coverCount
    : 0;
  const effectiveVisualCoverFailedCount = typeof effectiveSelectedVisualReview?.failedCoverCount === 'number'
    ? effectiveSelectedVisualReview.failedCoverCount
    : 0;
  const effectiveVisualCoverRequestedCount = typeof effectiveSelectedVisualReview?.requestedCoverCount === 'number'
    ? effectiveSelectedVisualReview.requestedCoverCount
    : (typeof effectiveSelectedVisualReview?.currentCoverTotal === 'number' ? effectiveSelectedVisualReview.currentCoverTotal : null);
  const effectiveVisualCoverCurrentIndex = typeof effectiveSelectedVisualReview?.currentCoverIndex === 'number'
    ? effectiveSelectedVisualReview.currentCoverIndex
    : null;
  const effectiveVisualCoverCurrentTotal = typeof effectiveSelectedVisualReview?.currentCoverTotal === 'number'
    ? effectiveSelectedVisualReview.currentCoverTotal
    : null;
  const showVisualCoverProgressSummary = typeof effectiveVisualCoverRequestedCount === 'number' && effectiveVisualCoverRequestedCount > 0;
  const hasRunningLiveReview = Boolean(activeLiveReviewSnapshot?.username)
    && (visualLoading || visualJob?.status === 'running' || visualJob?.status === 'queued');
  const isViewingVisualReviewHistory = visualReviewSelection.mode === 'history' && Boolean(effectiveSelectedVisualReview);
  const canNavigateToPreviousReview = visualReviewSelection.mode === 'history'
    ? effectiveSelectedHistoryIndex > 0
    : visualReviewHistory.length > 0;
  const canNavigateToNextReview = visualReviewSelection.mode === 'history'
    && effectiveSelectedHistoryIndex >= 0
    && effectiveSelectedHistoryIndex < visualReviewHistory.length - 1;
  const canReturnToLiveReview = hasRunningLiveReview && visualReviewSelection.mode !== 'live';
  const visualReviewPositionLabel = isViewingVisualReviewHistory && effectiveSelectedHistoryIndex >= 0
    ? `${effectiveSelectedHistoryIndex + 1} / ${visualReviewHistory.length}`
    : (hasRunningLiveReview ? '实时' : '—');
  const visualSummary = visualJob?.result?.summary || visualJob?.partial_result?.summary || null;
  const visualPassedCount = typeof visualSummary?.passed === 'number'
    ? visualSummary.passed
    : Object.values(visualResults).filter((review) => review?.success !== false && review?.decision !== 'Reject').length;
  const visualRejectedCount = typeof visualSummary?.rejected === 'number'
    ? visualSummary.rejected
    : Object.values(visualResults).filter((review) => review?.decision === 'Reject').length;
  const visualFailedCount = typeof visualSummary?.failed === 'number'
    ? visualSummary.failed
    : Object.values(visualResults).filter((review) => review?.success === false).length;
  const showVisualReviewDesk = visualProgress.total > 0
    || visualReviewHistory.length > 0
    || Object.keys(visualResults).length > 0
    || Boolean(activeLiveReviewSnapshot?.username);
  const visualReviewProgressPercent = visualProgress.total > 0
    ? Math.min(100, Math.max(0, (visualProgress.done / visualProgress.total) * 100))
    : 0;

  const handleVisualReviewNavigation = (direction) => {
    if (direction === 'prev') {
      if (visualReviewSelection.mode !== 'history') {
        if (visualReviewHistory.length > 0) {
          selectVisualReviewHistoryByIndex(visualReviewHistory.length - 1);
        }
        return;
      }
      selectVisualReviewHistoryByIndex(effectiveSelectedHistoryIndex - 1);
      return;
    }

    if (visualReviewSelection.mode !== 'history') {
      return;
    }
    selectVisualReviewHistoryByIndex(effectiveSelectedHistoryIndex + 1);
  };

  return (
    <div className="min-h-screen bg-[#FAFAFA] px-5 pb-10 pt-5 text-gray-900 md:px-10 md:pb-16">
      <div className="relative mx-auto max-w-6xl">
        <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[520px] overflow-hidden">
          <div className="absolute left-[-8%] top-10 h-72 w-72 rounded-full bg-white blur-3xl" />
          <div className="absolute right-[-4%] top-20 h-80 w-80 rounded-full bg-slate-200/70 blur-3xl" />
          <div className="absolute left-1/3 top-0 h-64 w-64 rounded-full bg-stone-200/50 blur-3xl" />
        </div>

        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="px-1 pb-6 pt-8 text-center md:pt-12"
        >
          <div className="inline-flex items-center gap-2 rounded-full border border-gray-200/70 bg-white/85 px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-500 shadow-[0_1px_2px_rgba(15,23,42,0.03)] backdrop-blur">
            Workflow Console
          </div>
          <h1 className="mt-4 flex flex-col items-center justify-center gap-4 text-4xl font-semibold tracking-[-0.05em] text-gray-900 md:flex-row md:text-5xl">
            <span className="flex h-16 w-16 items-center justify-center rounded-[22px] border border-gray-200/70 bg-white shadow-[0_1px_3px_rgba(15,23,42,0.05),0_18px_40px_rgba(15,23,42,0.04)]">
              <Play className="h-8 w-8 fill-current text-gray-900" />
            </span>
            <span>社交媒体数据采集器</span>
          </h1>
          <p className="mt-4 text-xs font-semibold uppercase tracking-[0.28em] text-gray-500 md:text-sm">
            Social Media Scraper & Analyzer
          </p>
        </motion.div>

        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 md:items-start">
          <div className="space-y-5">
            <motion.div
              custom={0}
              initial="hidden"
              animate="visible"
              variants={bentoVariants}
              className={bentoCardClassName}
            >
              <div className="mx-auto max-w-xl text-center">
                <div className="mb-5 inline-flex h-14 w-14 items-center justify-center rounded-[20px] border border-gray-200/70 bg-gray-50 text-gray-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
                  <UploadCloud className="h-6 w-6" />
                </div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Input Gateway</p>
                <h3 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-gray-900">上传 Excel 文件</h3>
                <p className="mt-3 text-sm leading-6 text-gray-500">
                  上传包含社交媒体链接的文件以自动识别平台并填充输入框。
                </p>

                <div className="relative mt-8 cursor-pointer group">
                  <input
                    type="file"
                    accept=".xlsx, .xls"
                    onChange={handleFileUpload}
                    disabled={uploading}
                    className="absolute inset-0 z-10 h-full w-full cursor-pointer rounded-[24px] opacity-0 disabled:cursor-not-allowed"
                  />
                  <div className={`pointer-events-none rounded-[24px] border border-dashed px-6 py-12 transition-all duration-200 ${
                    uploading
                      ? 'border-gray-300 bg-gray-100/80'
                      : 'border-gray-300 bg-gray-50/90 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)] group-hover:-translate-y-px group-hover:border-gray-400 group-hover:bg-white group-hover:shadow-[0_14px_32px_rgba(15,23,42,0.07)]'
                  }`}>
                    <p className="text-sm font-semibold text-gray-900">
                      {uploading ? '正在处理文件...' : '点击或拖拽文件到此处上传'}
                    </p>
                    <p className="mt-2 text-xs uppercase tracking-[0.2em] text-gray-400">.xlsx / .xls</p>
                  </div>
                </div>

                <AnimatePresence>
                  {uploadProgress && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className={`mt-5 overflow-hidden rounded-[22px] border p-4 text-left ${
                        uploadProgress.phase === 'completed'
                          ? 'border-emerald-200/80 bg-emerald-50/70'
                          : uploadProgress.phase === 'failed'
                            ? 'border-rose-200/80 bg-rose-50/80'
                            : 'border-gray-200/80 bg-gray-50/80'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">{uploadProgress.label}</p>
                          <p className="mt-1 text-xs text-gray-500">
                            {uploadProgress.fileName}
                            {uploadProgress.fileSize ? ` · ${formatUploadFileSize(uploadProgress.fileSize)}` : ''}
                          </p>
                        </div>
                        <div className="rounded-full bg-white/80 px-3 py-1 text-xs font-semibold text-gray-700 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
                          {uploadProgress.badge || `${Math.max(0, Math.min(100, Math.round(uploadProgress.percent || 0)))}%`}
                        </div>
                      </div>
                      <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-white/90">
                        <motion.div
                          className={`h-full rounded-full ${
                            uploadProgress.phase === 'completed'
                              ? 'bg-emerald-500'
                              : uploadProgress.phase === 'failed'
                                ? 'bg-rose-500'
                                : 'bg-gray-900'
                          }`}
                          initial={false}
                          animate={{ width: `${Math.max(4, Math.min(100, uploadProgress.percent || 0))}%` }}
                          transition={{ duration: 0.25, ease: 'easeOut' }}
                        />
                      </div>
                      <p className="mt-3 text-xs leading-5 text-gray-500">
                        上传大文件或多 sheet 工作簿时，通常会先很快传完文件，再花几秒做解析与校验。
                      </p>
                    </motion.div>
                  )}

                  {uploadResult && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="mt-6 overflow-hidden rounded-[24px] border border-gray-200/70 bg-gray-50/70 p-5 text-left"
                    >
                      <p className="mb-4 flex items-center gap-2 text-sm font-semibold text-gray-900">
                        <CheckCircle className="h-4 w-4 text-emerald-500" /> 分析结果
                      </p>
                      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                        <div className="rounded-2xl border border-gray-200/70 bg-white p-3 text-center shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-gray-400">TikTok</div>
                          <div className="mt-2 text-lg font-semibold text-gray-900">{uploadResult.stats.TikTok || 0}</div>
                        </div>
                        <div className="rounded-2xl border border-gray-200/70 bg-white p-3 text-center shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-gray-400">Instagram</div>
                          <div className="mt-2 text-lg font-semibold text-gray-900">{uploadResult.stats.Instagram || 0}</div>
                        </div>
                        <div className="rounded-2xl border border-gray-200/70 bg-white p-3 text-center shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-gray-400">YouTube</div>
                          <div className="mt-2 text-lg font-semibold text-gray-900">{uploadResult.stats.YouTube || 0}</div>
                        </div>
                        <div className="rounded-2xl border border-gray-200/70 bg-white p-3 text-center shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                          <div className="text-[11px] uppercase tracking-[0.18em] text-gray-400">Unknown</div>
                          <div className="mt-2 text-lg font-semibold text-gray-900">{uploadResult.stats.Unknown || 0}</div>
                        </div>
                      </div>
                      <p className="mt-4 flex items-center justify-center gap-1.5 text-sm font-medium text-emerald-600">
                        <CheckCircle className="h-4 w-4" /> 已根据文件内容自动填充输入框
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>

            <motion.div
              custom={1}
              initial="hidden"
              animate="visible"
              variants={bentoVariants}
              className={bentoCardClassName}
            >
              <div className="flex flex-col gap-8">
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Batch Window</p>
                    <label className="mt-3 flex items-center gap-3 text-xl font-semibold tracking-[-0.03em] text-gray-900">
                      本次抓取数量
                      <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-sm font-semibold text-gray-700">
                        {batchLimit}
                      </span>
                    </label>
                    <p className="mt-3 max-w-md text-sm leading-6 text-gray-500">
                      拖动滑块选择本次要从列表中处理多少个博主或链接，最大 100。
                    </p>
                  </div>
                  <label className={`${optionPillClassName} justify-center md:justify-start`}>
                    <input
                      type="checkbox"
                      checked={forceRefresh}
                      onChange={e => setForceRefresh(e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-gray-900"
                    />
                    <span>强制刷新缓存</span>
                  </label>
                </div>

                <div className="rounded-[24px] border border-gray-200/70 bg-gray-50/70 px-5 py-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)]">
                  <input
                    type="range"
                    min="1"
                    max="100"
                    value={batchLimit}
                    onChange={(e) => setBatchLimit(parseInt(e.target.value))}
                    className="h-2 w-full cursor-pointer appearance-none rounded-full bg-gray-200 accent-gray-900"
                  />
                </div>
              </div>
            </motion.div>
          </div>

          <motion.div
            custom={2}
            initial="hidden"
            animate="visible"
            variants={bentoVariants}
            className={`${bentoCardClassName} h-full`}
          >
            <div className="flex h-full flex-col gap-8">
              <div className="border-b border-gray-100 pb-8">
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Platform Setup</p>
                    <h3 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-gray-900">选择平台并配置采集参数</h3>
                    <p className="mt-3 max-w-xl text-sm leading-6 text-gray-500">
                      切换目标平台后，下方表单保持原有行为和字段，只更新布局与交互质感。
                    </p>
                  </div>
                </div>

                <div className="mt-6 inline-flex w-full rounded-2xl bg-gray-100/90 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
                  {['tiktok', 'instagram', 'youtube'].map(tab => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`relative flex-1 cursor-pointer rounded-xl px-4 py-3 text-sm font-semibold transition-colors ${
                        activeTab === tab ? 'text-gray-900' : 'text-gray-500 hover:text-gray-700'
                      }`}
                    >
                      {activeTab === tab && (
                        <motion.div
                          layoutId="activeTab"
                          className="absolute inset-0 rounded-xl bg-white shadow-[0_1px_2px_rgba(15,23,42,0.06),0_12px_30px_rgba(15,23,42,0.08)]"
                          transition={{ type: "spring", stiffness: 320, damping: 32 }}
                        />
                      )}
                      <span className="relative z-10 flex items-center justify-center gap-2">
                        {tab === 'youtube' && <Youtube className="h-4 w-4" />}
                        {tab === 'instagram' && <Instagram className="h-4 w-4" />}
                        {tab === 'tiktok' && <Square className="h-4 w-4" />}
                        {tab === 'tiktok' ? 'TikTok' : tab === 'instagram' ? 'Instagram' : 'YouTube'}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <AnimatePresence mode="wait">
                {activeTab === 'tiktok' && (
                  <motion.div
                    key="tiktok"
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 10 }}
                    className="space-y-6"
                  >
                    <h4 className="text-xl font-semibold tracking-[-0.03em] text-gray-900">TikTok 采集配置</h4>
                    <div className="space-y-5">
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700">用户名列表 (逗号分隔)</label>
                        <input
                          type="text"
                          value={tiktokProfiles}
                          onChange={e => setTiktokProfiles(e.target.value)}
                          placeholder="_lilheat_, brooklynreviewsxoxo"
                          className={formFieldClassName}
                        />
                      </div>
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700">单账号抓取上限 (Limit per profile)</label>
                        <input
                          type="number"
                          value={tiktokLimit}
                          onChange={e => setTiktokLimit(e.target.value)}
                          className={compactFieldClassName}
                        />
                      </div>
                      <div className="flex flex-wrap gap-3 pt-1">
                        <label className={optionPillClassName}>
                          <input type="checkbox" checked={tiktokOptions.excludePinnedPosts} onChange={e => setTiktokOptions({...tiktokOptions, excludePinnedPosts: e.target.checked})} className="rounded border-gray-300 text-gray-900" />
                          排除置顶视频
                        </label>
                        <label className={optionPillClassName}>
                          <input type="checkbox" checked={tiktokOptions.downloadVideos} onChange={e => setTiktokOptions({...tiktokOptions, downloadVideos: e.target.checked})} className="rounded border-gray-300 text-gray-900" />
                          下载视频文件
                        </label>
                        <label className={optionPillClassName}>
                          <input type="checkbox" checked={tiktokOptions.downloadCovers} onChange={e => setTiktokOptions({...tiktokOptions, downloadCovers: e.target.checked})} className="rounded border-gray-300 text-gray-900" />
                          下载封面图
                        </label>
                        <label className={optionPillClassName}>
                          <input type="checkbox" checked={tiktokOptions.downloadAvatars} onChange={e => setTiktokOptions({...tiktokOptions, downloadAvatars: e.target.checked})} className="rounded border-gray-300 text-gray-900" />
                          下载头像
                        </label>
                      </div>
                    </div>
                  </motion.div>
                )}

                {activeTab === 'instagram' && (
                  <motion.div
                    key="instagram"
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 10 }}
                    className="space-y-6"
                  >
                    <h4 className="text-xl font-semibold tracking-[-0.03em] text-gray-900">Instagram 采集配置</h4>
                    <div className="space-y-5">
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700">用户名列表 (逗号分隔)</label>
                        <input
                          type="text"
                          value={instagramUsernames}
                          onChange={e => setInstagramUsernames(e.target.value)}
                          placeholder="babeidii, kuleshova"
                          className={formFieldClassName}
                        />
                      </div>
                      <div className="pt-1">
                        <label className={`${optionPillClassName} inline-flex`}>
                          <input type="checkbox" checked={instagramOptions.includeAbout} onChange={e => setInstagramOptions({...instagramOptions, includeAbout: e.target.checked})} className="rounded border-gray-300 text-gray-900" />
                          包含详细简介 (About Section)
                        </label>
                      </div>
                    </div>
                  </motion.div>
                )}

                {activeTab === 'youtube' && (
                  <motion.div
                    key="youtube"
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 10 }}
                    className="space-y-6"
                  >
                    <h4 className="text-xl font-semibold tracking-[-0.03em] text-gray-900">YouTube 采集配置</h4>
                    <div className="space-y-5">
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700">模式</label>
                        <select
                          value={youtubeMode}
                          onChange={e => setYoutubeMode(e.target.value)}
                          className={selectFieldClassName}
                        >
                          <option value="search">关键词搜索 (Search)</option>
                          <option value="channel">频道/视频链接 (Channel/URL)</option>
                        </select>
                      </div>
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700">{youtubeMode === 'search' ? '关键词' : '链接'} (逗号分隔)</label>
                        <input
                          type="text"
                          value={youtubeQuery}
                          onChange={e => setYoutubeQuery(e.target.value)}
                          placeholder={youtubeMode === 'search' ? "Crawlee, Apify" : "https://youtube.com/@Channel"}
                          className={formFieldClassName}
                        />
                      </div>
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700">结果数量限制</label>
                        <input
                          type="number"
                          value={youtubeLimit}
                          onChange={e => setYoutubeLimit(e.target.value)}
                          className={compactFieldClassName}
                        />
                      </div>
                      <div className="flex flex-wrap gap-3 pt-1">
                        <label className={optionPillClassName}>
                          <input type="checkbox" checked={youtubeOptions.downloadSubtitles} onChange={e => setYoutubeOptions({...youtubeOptions, downloadSubtitles: e.target.checked})} className="rounded border-gray-300 text-gray-900" />
                          下载字幕
                        </label>
                        <label className={optionPillClassName}>
                          <input type="checkbox" checked={youtubeOptions.hasCC} onChange={e => setYoutubeOptions({...youtubeOptions, hasCC: e.target.checked})} className="rounded border-gray-300 text-gray-900" />
                          仅限有字幕视频 (CC)
                        </label>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        </div>

        <motion.div
          custom={3}
          initial="hidden"
          animate="visible"
          variants={bentoVariants}
          className={`${bentoCardClassName} mt-5`}
        >
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Workspace</p>
              <h3 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-gray-900">运行工作台 / 结果工作台</h3>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-gray-500">
                主工作流只保留上传、配置、启动与任务进度；后续复核与导出通过明确入口进入结果工作台，不再继续向下堆叠。
              </p>
            </div>
            <div className="inline-flex w-full rounded-2xl bg-gray-100/90 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] lg:max-w-[360px]">
              <button
                type="button"
                onClick={() => setActiveWorkspace('run')}
                className={`flex-1 rounded-xl px-4 py-3 text-sm font-semibold transition-all duration-200 ${
                  activeWorkspace === 'run'
                    ? 'bg-white text-gray-900 shadow-[0_1px_2px_rgba(15,23,42,0.06),0_12px_30px_rgba(15,23,42,0.08)]'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                运行工作台
              </button>
              <button
                type="button"
                onClick={() => {
                  if (!result) return;
                  setActiveWorkspace('results');
                }}
                disabled={!result}
                className={`flex-1 rounded-xl px-4 py-3 text-sm font-semibold transition-all duration-200 ${
                  activeWorkspace === 'results'
                    ? 'bg-white text-gray-900 shadow-[0_1px_2px_rgba(15,23,42,0.06),0_12px_30px_rgba(15,23,42,0.08)]'
                    : 'text-gray-500 hover:text-gray-700'
                } ${!result ? 'cursor-not-allowed opacity-50' : ''}`}
              >
                结果工作台
              </button>
            </div>
          </div>
        </motion.div>

        {activeWorkspace === 'run' && (
          <>
            <motion.div
              custom={3}
              initial="hidden"
              animate="visible"
              variants={bentoVariants}
              className={`${bentoCardClassName} mt-5`}
            >
              <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Launch Panel</p>
                  <h3 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-gray-900">启动采集与查看任务进度</h3>
                  <p className="mt-3 max-w-2xl text-sm leading-6 text-gray-500">
                    当前交互和数据绑定保持不变，只将按钮、告警和任务反馈收敛进同一块操作面板。
                  </p>
                </div>
                <button
                  onClick={scrapeRunning ? handleCancelScrape : handleScrape}
                  className={`inline-flex min-w-[220px] cursor-pointer items-center justify-center gap-2 rounded-[20px] px-8 py-4 text-sm font-semibold transition-[transform,box-shadow,background-color] duration-200 ${
                    scrapeRunning
                      ? 'bg-rose-600 text-white shadow-[0_18px_40px_rgba(225,29,72,0.22)] hover:-translate-y-px hover:bg-rose-700'
                      : 'bg-gray-950 text-white shadow-[0_18px_40px_rgba(15,23,42,0.18)] hover:-translate-y-px hover:bg-gray-900'
                  }`}
                >
                  {scrapeRunning ? <XCircle className="h-5 w-5" /> : <Play className="h-5 w-5" />}
                  {scrapeRunning ? (scrapeJob?.id ? '取消采集' : '取消提交') : '开始采集 (Start Scraping)'}
                </button>
              </div>

              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-6 flex items-start gap-3 rounded-[22px] border border-rose-200/70 bg-rose-50/80 p-5 text-rose-800"
                  >
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                    <div>
                      <strong className="block mb-1">错误</strong>
                      <span className="text-sm">{error}</span>
                    </div>
                  </motion.div>
                )}

                {visualError && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mt-6 flex items-start gap-3 rounded-[22px] border border-amber-200/70 bg-amber-50/80 p-5 text-amber-800"
                  >
                    <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                    <div>
                      <strong className="block mb-1">视觉复核提示</strong>
                      <span className="text-sm">{visualError}</span>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              <div className="mt-6 space-y-3">
                {renderJobCard('采集任务进度', scrapeJob, 'info')}
                {renderJobCard('视觉复核任务进度', visualJob, 'warning')}
              </div>
            </motion.div>

            <motion.div
              custom={3}
              initial="hidden"
              animate="visible"
              variants={bentoVariants}
              className="mt-5 grid gap-5 xl:grid-cols-2"
            >
              {result && (
                <div className={`${bentoCardClassName} p-7`}>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Results Entry</p>
                  <h3 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-gray-900">结果工作台入口</h3>
                  <p className="mt-3 text-sm leading-6 text-gray-500">
                    当前已经有可继续操作的 {activeResultPlatform} 结果。复核、导出和运行快照改为进入结果工作台后再查看。
                  </p>
                  <div className="mt-5 flex flex-wrap gap-2">
                    <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-700">
                      {resultWorkspaceStatus}
                    </span>
                    <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-700">
                      {result.count} 条结果
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveWorkspace('results');
                      setActiveResultTab('overview');
                    }}
                    className="mt-6 inline-flex cursor-pointer items-center justify-center gap-2 rounded-full bg-gray-950 px-5 py-3 text-sm font-semibold text-white shadow-[0_16px_36px_rgba(15,23,42,0.16)] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-px hover:bg-gray-900 hover:shadow-[0_18px_34px_rgba(15,23,42,0.20)]"
                  >
                    进入结果工作台
                  </button>
                </div>
              )}

              <div className={`${bentoCardClassName} p-7`}>
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">Secondary Tool</p>
                <h3 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-gray-900">RuleSpec 不再挤占主工作流</h3>
                <p className="mt-3 text-sm leading-6 text-gray-500">
                  它仍可用，但现在是二级工具。只有在你明确打开时，才会展开 SOP 编译与字段匹配面板。
                </p>
                <button
                  type="button"
                  onClick={() => setShowTemplateWorkbench(true)}
                  className="mt-6 inline-flex cursor-pointer items-center justify-center gap-2 rounded-full border border-gray-200 bg-white px-5 py-3 text-sm font-semibold text-gray-700 shadow-[0_12px_24px_rgba(15,23,42,0.06)] transition-[transform,box-shadow,border-color,background-color] duration-200 hover:-translate-y-px hover:border-gray-300 hover:bg-gray-50 hover:shadow-[0_16px_28px_rgba(15,23,42,0.08)]"
                >
                  打开 RuleSpec 工具
                </button>
              </div>
            </motion.div>

            {showTemplateWorkbench && (
              <motion.div
                custom={3}
                initial="hidden"
                animate="visible"
                variants={bentoVariants}
                className={`${bentoCardClassName} mt-5`}
              >
                <div className="flex flex-col gap-6">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-gray-400">RuleSpec Compiler</p>
                      <h3 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-gray-900">输入审核需求，编译 RuleSpec 与字段匹配报告</h3>
                      <p className="mt-3 max-w-3xl text-sm leading-6 text-gray-500">
                        这里不会直接执行审核，只会把你的 SOP 编译成受限 RuleSpec，并给出 TikTok、Instagram、YouTube 的字段匹配结果。V1 strict mode 里 YouTube 会稳定标记为 unsupported。
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={() => setShowTemplateWorkbench(false)}
                        className="inline-flex cursor-pointer items-center justify-center rounded-full border border-gray-200 bg-white px-5 py-3 text-sm font-semibold text-gray-700 transition-colors hover:border-gray-300 hover:bg-gray-50"
                      >
                        返回主工作流
                      </button>
                      <button
                        type="button"
                        onClick={handleGenerateTemplates}
                        disabled={templateLoading}
                        className={`inline-flex min-w-[220px] cursor-pointer items-center justify-center gap-2 rounded-[20px] px-8 py-4 text-sm font-semibold transition-[transform,box-shadow,background-color] duration-200 ${
                          templateLoading
                            ? 'bg-gray-300 text-white shadow-none cursor-wait'
                            : 'bg-gray-950 text-white shadow-[0_18px_40px_rgba(15,23,42,0.18)] hover:-translate-y-px hover:bg-gray-900'
                        }`}
                      >
                        <RefreshCw className={`h-5 w-5 ${templateLoading ? 'animate-spin' : ''}`} />
                        {templateLoading ? '编译中...' : '编译 RuleSpec'}
                      </button>
                    </div>
                  </div>

                  <div className="rounded-[24px] border border-gray-200/70 bg-gray-50/70 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)] md:p-5">
                    <textarea
                      value={templateInput}
                      onChange={(e) => setTemplateInput(e.target.value)}
                      placeholder={TEMPLATE_PLACEHOLDER}
                      className={`${formFieldClassName} min-h-[260px] resize-y leading-6`}
                    />
                    <div className="mt-3 flex flex-col gap-2 text-xs text-gray-500 md:flex-row md:items-center md:justify-between">
                      <span>支持中英混合自由文本，建议按“目标 / 步骤 / 最终结果”结构输入。</span>
                      <span>{templateInput.trim().length} 字符</span>
                    </div>
                  </div>

                  <AnimatePresence>
                    {templateError && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="flex items-start gap-3 rounded-[22px] border border-rose-200/70 bg-rose-50/80 p-5 text-rose-800"
                      >
                        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" />
                        <div>
                          <strong className="mb-1 block">RuleSpec 编译失败</strong>
                          <span className="text-sm">{templateError}</span>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {templateResult && (
                    <div className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
                      <div className="space-y-4 rounded-[24px] border border-gray-200/70 bg-gray-50/70 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)]">
                        <div>
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Parse Summary</p>
                          <h4 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-gray-900">
                            {templateResult.parsed_sop?.goal || '未识别到审核目标'}
                          </h4>
                          <p className="mt-2 text-sm leading-6 text-gray-500">
                            共解析出 {parsedTemplateSteps.length} 个步骤。
                            {Array.isArray(templateResult?.rule_spec?.out_of_scope_actions) ? ` 范围外动作 ${templateResult.rule_spec.out_of_scope_actions.length} 条。` : ''}
                            {templateResult.output_dir ? ` 已写入 ${templateResult.output_dir}` : ''}
                          </p>
                        </div>

                        <div className="grid gap-3 sm:grid-cols-3">
                          {availableTemplatePlatforms.map((platform) => {
                            const summary = templateResult.field_match_report?.platforms?.[platform]?.summary || {};
                            return (
                              <button
                                key={platform}
                                type="button"
                                onClick={() => setTemplatePlatform(platform)}
                                className={`rounded-[22px] border p-4 text-left transition-[transform,border-color,box-shadow] duration-200 ${
                                  templatePlatform === platform
                                    ? 'border-gray-900 bg-white shadow-[0_18px_34px_rgba(15,23,42,0.08)]'
                                    : 'border-gray-200/80 bg-white hover:-translate-y-px hover:border-gray-300 hover:shadow-[0_10px_24px_rgba(15,23,42,0.05)]'
                                }`}
                              >
                                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-400">
                                  {formatTemplatePlatformLabel(platform)}
                                </p>
                                <div className="mt-3 space-y-2 text-sm text-gray-600">
                                  <div className="flex items-center justify-between">
                                    <span>已匹配</span>
                                    <span className="font-semibold text-emerald-700">{summary.matched || 0}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span>部分匹配</span>
                                    <span className="font-semibold text-amber-700">{summary.partial || 0}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span>能力缺口</span>
                                    <span className="font-semibold text-orange-700">{summary.missing_capabilities || 0}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span>解析歧义</span>
                                    <span className="font-semibold text-sky-700">{summary.ambiguous || 0}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span>当前不支持</span>
                                    <span className="font-semibold text-rose-700">{summary.unsupported || 0}</span>
                                  </div>
                                  <div className="flex items-center justify-between">
                                    <span>敏感属性禁用</span>
                                    <span className="font-semibold text-slate-700">{summary.blocked_sensitive_attribute || 0}</span>
                                  </div>
                                </div>
                              </button>
                            );
                          })}
                        </div>

                        <div className="rounded-[22px] border border-gray-200/80 bg-white p-4">
                          <p className="text-sm font-semibold text-gray-900">解析步骤</p>
                          <div className="mt-3 space-y-3">
                            {parsedTemplateSteps.map((step) => (
                              <div key={step.title} className="rounded-2xl border border-gray-200/70 bg-gray-50/70 p-3">
                                <p className="text-sm font-semibold text-gray-900">{step.title}</p>
                                <p className="mt-1 text-xs text-gray-500">
                                  已识别 {step.rule_count || 0} 条规则
                                </p>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4 rounded-[24px] border border-gray-200/70 bg-white p-5 shadow-[0_1px_3px_rgba(15,23,42,0.04),0_18px_42px_rgba(15,23,42,0.05)]">
                        <div className="flex flex-col gap-2 border-b border-gray-100 pb-4 md:flex-row md:items-end md:justify-between">
                          <div>
                            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Platform Match Report</p>
                            <h4 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-gray-900">
                              {selectedTemplate ? `${formatTemplatePlatformLabel(templatePlatform)} 匹配报告` : '选择平台查看报告'}
                            </h4>
                          </div>
                          {templateResult?.rule_spec?.final_logic && (
                            <div className="rounded-full border border-gray-200 bg-gray-50 px-4 py-2 text-xs font-medium text-gray-600">
                              Final Logic: {templateResult.rule_spec.final_logic}
                            </div>
                          )}
                        </div>

                        {selectedTemplate && (
                          <>
                            <div className="grid gap-3 md:grid-cols-2">
                              <div className="rounded-[22px] border border-gray-200/80 bg-gray-50/70 p-4">
                                <p className="text-sm font-semibold text-gray-900">字段映射依据</p>
                                <div className="mt-3 flex flex-wrap gap-2">
                                  {(selectedTemplate.mapping_basis || []).map((item) => (
                                    <span key={item} className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600">
                                      {item}
                                    </span>
                                  ))}
                                </div>
                              </div>
                              <div className="rounded-[22px] border border-gray-200/80 bg-gray-50/70 p-4">
                                <p className="text-sm font-semibold text-gray-900">平台结论</p>
                                <p className="mt-3 text-sm leading-6 text-gray-600">
                                  {selectedTemplate.platform_note || `当前共有 ${selectedTemplateGaps.length} 条规则需要人工确认、补字段或补采集能力。`}
                                </p>
                              </div>
                            </div>

                            <div className="space-y-3">
                              {selectedTemplateChecks.map((check) => (
                                <div key={check.rule_id} className="rounded-[22px] border border-gray-200/80 bg-gray-50/60 p-4">
                                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                                    <div className="min-w-0">
                                      <p className="text-sm font-semibold text-gray-900">{check.source_text}</p>
                                      <p className="mt-1 text-xs text-gray-500">
                                        {check.step_title} · {check.rule_type}
                                      </p>
                                    </div>
                                    <span className={`inline-flex shrink-0 items-center rounded-full border px-3 py-1 text-xs font-semibold ${getTemplateStatusClassName(check.status)}`}>
                                      {formatTemplateStatusLabel(check.status)}
                                    </span>
                                  </div>

                                  <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                                    <div className="rounded-2xl border border-gray-200/70 bg-white p-3">
                                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-400">Fields</p>
                                      <p className="mt-2 text-sm leading-6 text-gray-600 break-all">
                                        {Array.isArray(check.matched_fields) && check.matched_fields.length > 0 ? check.matched_fields.join(', ') : '当前没有稳定字段支撑'}
                                      </p>
                                    </div>
                                    <div className="rounded-2xl border border-gray-200/70 bg-white p-3">
                                      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-400">Capabilities / Notes</p>
                                      <p className="mt-2 text-sm leading-6 text-gray-600">
                                        {Array.isArray(check.required_capabilities) && check.required_capabilities.length > 0 ? `需要 ${check.required_capabilities.join(', ')}。` : ''}
                                        {Array.isArray(check.missing_capabilities) && check.missing_capabilities.length > 0 ? ` 缺口 ${check.missing_capabilities.join(', ')}。` : ''}
                                        {check.notes ? ` ${check.notes}` : ' 无额外说明'}
                                      </p>
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>

                            {selectedTemplateBlockedRules.length > 0 && (
                              <div className="rounded-[22px] border border-slate-200/80 bg-slate-50/90 p-4">
                                <p className="text-sm font-semibold text-slate-900">已阻止的敏感属性规则</p>
                                <div className="mt-3 space-y-2">
                                  {selectedTemplateBlockedRules.map((rule) => (
                                    <div key={rule.rule_id} className="rounded-2xl border border-slate-200/80 bg-white p-3 text-sm text-slate-700">
                                      <p className="font-medium text-slate-900">{rule.source_text}</p>
                                      <p className="mt-1 text-xs text-slate-500">{rule.notes || rule.policy_reason || '该规则不应自动化执行'}</p>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </motion.div>
            )}
          </>
        )}

        <AnimatePresence>
          {result && activeWorkspace === 'results' && (
            <motion.div
              custom={4}
              initial="hidden"
              animate="visible"
              exit="hidden"
              variants={bentoVariants}
              className={`${bentoCardClassName} mt-5`}
            >
              <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl">
                  <div className="inline-flex items-center gap-3 rounded-full border border-gray-200 bg-gray-50 px-4 py-2 text-sm font-medium text-gray-700">
                    <span className={`flex h-9 w-9 items-center justify-center rounded-full ${result.cached ? 'bg-amber-100 text-amber-600' : 'bg-emerald-100 text-emerald-600'}`}>
                      {scrapeRunning || result.is_partial ? <Clock className="h-5 w-5" /> : <CheckCircle className="h-5 w-5" />}
                    </span>
                    <span>
                      {scrapeRunning
                        ? (result.is_partial ? '当前已返回部分结果' : '本次任务运行中，暂用上一次结果')
                        : (result.cached ? '已加载缓存结果' : '采集成功')}
                    </span>
                  </div>
                  <h3 className="mt-5 text-3xl font-semibold tracking-[-0.04em] text-gray-900">
                    {activeResultPlatform} 数据面板
                  </h3>
                  <p className="mt-3 text-sm leading-6 text-gray-500 md:text-base">
                    {result.is_partial
                      ? `当前采集仍在进行，下面展示的是已经返回的 ${activeResultPlatform} 部分结果。`
                      : showingPreviousResultWhileRunning
                        ? `当前采集仍在进行，下面暂时保留上一次可用的 ${activeResultPlatform} 结果供查看；这不代表本次任务已失败。`
                        : result.used_fallback
                        ? `当前页面展示的是后端自动回退到的最近一次可用 ${activeResultPlatform} 结果。`
                        : result.stale_result
                          ? `当前页面展示的是最近一次可用但已标记为旧的 ${activeResultPlatform} 结果。`
                          : scrapeRunning
                            ? `当前采集仍在进行，下面显示的是最近一次可继续操作的 ${activeResultPlatform} 结果。`
                            : (result.cached ? `当前缓存结果共 ${result.count} 条数据。` : `共采集到 ${result.count} 条数据。`)}
                  </p>
                  {resultBannerMessage && (
                    <p className={`mt-3 text-sm font-medium ${resultBannerToneClassName}`}>
                      {showingPreviousResultWhileRunning ? `本次任务进度：${resultBannerMessage}` : resultBannerMessage}
                    </p>
                  )}
                  {failedBatchSummary && (
                    <div className="mt-3 max-w-3xl rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-sm leading-6 text-amber-900">
                      {failedBatchSummary}
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap gap-2">
                    {result.is_partial && (
                      <span className="inline-flex items-center rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-800">
                        部分结果
                      </span>
                    )}
                    {showingPreviousResultWhileRunning ? (
                      <span className="inline-flex items-center rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-800">
                        沿用上次结果
                      </span>
                    ) : null}
                    {!showingPreviousResultWhileRunning && result.cached && (
                      <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">
                        缓存结果
                      </span>
                    )}
                    {!showingPreviousResultWhileRunning && result.stale_result && (
                      <span className="inline-flex items-center rounded-full border border-amber-200 bg-white px-3 py-1 text-xs font-medium text-amber-800">
                        旧结果
                      </span>
                    )}
                    {!showingPreviousResultWhileRunning && result.used_fallback && (
                      <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-medium text-amber-800">
                        回退快照
                      </span>
                    )}
                    {!result.is_partial && !showingPreviousResultWhileRunning && !result.cached && !result.stale_result && !result.used_fallback && (
                      <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800">
                        最新完成结果
                      </span>
                    )}
                    {savedFinalReviewArtifactsAvailable && (
                      <span className="inline-flex items-center rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-700">
                        已发现可复用最终复核 artifact
                      </span>
                    )}
                  </div>
                </div>
                <div className="rounded-[22px] border border-gray-200/70 bg-gray-50/80 px-5 py-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.95)]">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Result Count</p>
                  <p className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-gray-900">{result.count}</p>
                </div>
              </div>

              <div className="mt-6 grid gap-3 lg:grid-cols-2">
                {resultStateGuidance.map((item) => (
                  <div
                    key={item.key}
                    className={`rounded-[22px] border px-4 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)] ${
                      item.tone === 'warning'
                        ? 'border-amber-200/80 bg-amber-50/80'
                        : item.tone === 'success'
                          ? 'border-emerald-200/80 bg-emerald-50/70'
                          : 'border-sky-200/80 bg-sky-50/70'
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="inline-flex items-center rounded-full border border-white/70 bg-white/80 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-600">
                        {item.label}
                      </span>
                    </div>
                    <h4 className="mt-3 text-base font-semibold text-gray-900">{item.title}</h4>
                    <p className="mt-2 text-sm leading-6 text-gray-700">{item.description}</p>
                  </div>
                ))}
              </div>

              <div className="mt-8">
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <div className="inline-flex w-full rounded-2xl bg-gray-100/90 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] md:max-w-[520px]">
                    {resultTabOptions.map((item) => {
                      const selected = activeResultTab === item.key;
                      return (
                        <button
                          key={item.key}
                          type="button"
                          onClick={() => setActiveResultTab(item.key)}
                          className={`flex-1 rounded-xl px-4 py-3 text-center text-sm font-semibold transition-all duration-200 ${
                            selected
                              ? 'bg-white text-gray-900 shadow-[0_1px_2px_rgba(15,23,42,0.06),0_12px_30px_rgba(15,23,42,0.08)]'
                              : 'text-gray-500 hover:text-gray-700'
                          }`}
                        >
                          {item.label}
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-sm text-gray-500">
                    当前视图：
                    <span className="font-medium text-gray-700"> {activeResultTabLabel}</span>
                    。概览只保留摘要，视觉复核与导出交接各自归位。
                  </p>
                </div>

                {activeResultTab === 'overview' && (
                  <div className="mt-6 space-y-4">
                    <div className="rounded-[24px] border border-gray-200/70 bg-[#FCFCFC] p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04),0_16px_40px_rgba(15,23,42,0.04)] md:p-7">
                      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                        <div className="rounded-2xl border border-gray-200/80 bg-white px-4 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Result Count</p>
                          <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-gray-900">{result.count}</p>
                        </div>
                        <div className="rounded-2xl border border-gray-200/80 bg-white px-4 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Review Coverage</p>
                          <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-gray-900">
                            {resultProfileReviews.length > 0
                              ? (result.is_partial ? `${resultProfileReviews.length} / ${resultRequestedTotal}` : resultRequestedTotal)
                              : '—'}
                          </p>
                        </div>
                        <div className="rounded-2xl border border-gray-200/80 bg-white px-4 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Passed</p>
                          <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-emerald-600">{resultPassedCount}</p>
                        </div>
                        <div className="rounded-2xl border border-gray-200/80 bg-white px-4 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Rejected</p>
                          <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-rose-600">{resultRejectedCount}</p>
                        </div>
                      </div>
                    </div>

                    <div className="max-w-[460px] rounded-[24px] border border-gray-200/80 bg-white px-5 py-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Next Action</p>
                      <h4 className="mt-2 text-base font-semibold text-gray-900">当前最该做什么</h4>
                      <p className="mt-3 text-sm leading-6 text-gray-500">
                        {visualReviewCompleted || hasFinalReviewExport
                          ? (hasInMemoryFinalReviewData
                            ? '当前页面内已有完整初筛 + 视觉复核输入，下一步进入导出交接即可导出 final-review Excel。'
                            : '后端已保存可复用 artifact，下一步进入导出交接即可继续 final-review 导出。')
                          : hasVisualReviewCandidates
                            ? `当前有 ${visualReviewCandidates.length} 个候选账号可做视觉复核，建议先进入视觉复核工作台。`
                            : result.is_partial
                              ? '采集仍在继续。下一步建议返回运行工作台观察任务进度，或先留在概览看增量结果。'
                              : '当前没有新的视觉复核动作需要推进，下一步建议进入导出交接做结果导出与交接。'}
                      </p>
                      <div className="mt-4">
                        {visualReviewCompleted || hasFinalReviewExport ? (
                          <button
                            type="button"
                            onClick={() => setActiveResultTab('export-handoff')}
                            className="inline-flex cursor-pointer items-center justify-center rounded-full bg-gray-950 px-5 py-3 text-sm font-semibold text-white shadow-[0_16px_36px_rgba(15,23,42,0.16)] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-px hover:bg-gray-900"
                          >
                            前往导出交接
                          </button>
                        ) : hasVisualReviewCandidates ? (
                          <button
                            type="button"
                            onClick={() => setActiveResultTab('visual-review')}
                            className="inline-flex cursor-pointer items-center justify-center rounded-full bg-gray-950 px-5 py-3 text-sm font-semibold text-white shadow-[0_16px_36px_rgba(15,23,42,0.16)] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-px hover:bg-gray-900"
                          >
                            前往视觉复核
                          </button>
                        ) : result.is_partial ? (
                          <button
                            type="button"
                            onClick={() => setActiveWorkspace('run')}
                            className="inline-flex cursor-pointer items-center justify-center rounded-full border border-gray-200 bg-white px-5 py-3 text-sm font-semibold text-gray-700 shadow-[0_12px_24px_rgba(15,23,42,0.06)] transition-[transform,box-shadow,border-color,background-color] duration-200 hover:-translate-y-px hover:border-gray-300 hover:bg-gray-50"
                          >
                            返回运行工作台
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setActiveResultTab('export-handoff')}
                            className="inline-flex cursor-pointer items-center justify-center rounded-full border border-gray-200 bg-white px-5 py-3 text-sm font-semibold text-gray-700 shadow-[0_12px_24px_rgba(15,23,42,0.06)] transition-[transform,box-shadow,border-color,background-color] duration-200 hover:-translate-y-px hover:border-gray-300 hover:bg-gray-50"
                          >
                            查看导出交接
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {activeResultTab === 'profiles' && (
                  <div className="mt-6">
                    {resultProfileReviews.length > 0 ? (
                      renderProfileCards()
                    ) : (
                      <div className="rounded-[24px] border border-dashed border-gray-200/80 bg-gray-50/70 px-6 py-12 text-center text-sm text-gray-500">
                        当前还没有可展示的博主卡片结果。
                      </div>
                    )}
                  </div>
                )}

                {activeResultTab === 'visual-review' && (
                  <div className="mt-6 space-y-4">
                    <div className="rounded-[24px] border border-gray-200/80 bg-white px-5 py-5 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Visual Review Mode</p>
                          <h4 className="mt-2 text-base font-semibold text-gray-900">视觉复核</h4>
                          <p className="mt-2 text-sm leading-6 text-gray-500">
                            {hasVisualReviewCandidates
                              ? visualReviewRecommendation.text
                              : '当前没有新的候选账号可进入视觉复核；如果之前已经启动过任务，下方仍会保留 desk 与历史队列。'}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {[
                            { value: VISUAL_REVIEW_MODE_SIMPLE, label: '简单', hint: '单九宫格，最多 9 张' },
                            { value: VISUAL_REVIEW_MODE_AUTO, label: '自动推荐', hint: '按可用图数自动升降级' },
                            { value: VISUAL_REVIEW_MODE_ENHANCED, label: '加强', hint: '双九宫格，最多 18 张' },
                          ].map((option) => {
                            const selected = visualReviewMode === option.value;
                            return (
                              <button
                                key={option.value}
                                type="button"
                                onClick={() => setVisualReviewMode(option.value)}
                                className={`rounded-2xl border px-4 py-3 text-left transition ${
                                  selected
                                    ? 'border-gray-900 bg-gray-900 text-white shadow-[0_10px_24px_rgba(15,23,42,0.16)]'
                                    : 'border-gray-200 bg-gray-50 text-gray-700 hover:border-gray-300 hover:bg-white'
                                }`}
                              >
                                <div className="text-sm font-semibold">{option.label}</div>
                                <div className={`mt-1 text-xs ${selected ? 'text-gray-200' : 'text-gray-500'}`}>{option.hint}</div>
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      {hasVisualReviewCandidates && (
                        <button
                          type="button"
                          onClick={handleVisualReview}
                          disabled={visualLoading}
                          className="mt-5 inline-flex cursor-pointer items-center justify-center gap-2 rounded-full bg-gray-950 px-5 py-3 text-sm font-semibold text-white shadow-[0_16px_36px_rgba(15,23,42,0.16)] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-px hover:bg-gray-900 hover:shadow-[0_18px_34px_rgba(15,23,42,0.20)] disabled:cursor-not-allowed disabled:opacity-70"
                        >
                          {visualLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                          {visualLoading
                            ? '视觉复核进行中...'
                            : `开始视觉复核（${visualReviewMode === VISUAL_REVIEW_MODE_SIMPLE ? '简单' : visualReviewMode === VISUAL_REVIEW_MODE_ENHANCED ? '加强' : '自动推荐'}）`}
                        </button>
                      )}
                    </div>

                    {showVisualReviewDesk ? (
                      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_340px] 2xl:items-start">
                        <motion.div
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="rounded-[24px] border border-gray-200/70 bg-white p-5 shadow-[0_1px_3px_rgba(15,23,42,0.04),0_18px_42px_rgba(15,23,42,0.05)] md:p-6"
                        >
                          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                            <div>
                              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Visual Review Desk</p>
                              <h4 className="mt-2 text-xl font-semibold tracking-[-0.03em] text-gray-900">九宫格推理日志</h4>
                              <p className="mt-2 text-sm leading-6 text-gray-500">
                                当前主面板支持停留在刚完成的博主上回看，也可以一键切回实时复核对象。
                              </p>
                            </div>
                            <div className="flex flex-wrap items-center justify-end gap-2">
                              <div className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600">
                                {effectiveSelectedVisualReview?.username || (visualLoading ? '等待首个对象' : '视觉复核待命')}
                              </div>
                              {canReturnToLiveReview && (
                                <button
                                  type="button"
                                  onClick={handleReturnToLiveReview}
                                  className="inline-flex cursor-pointer items-center rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:border-gray-300 hover:bg-gray-50"
                                >
                                  回到当前复核中
                                </button>
                              )}
                            </div>
                          </div>

                          <div className="mt-5 flex flex-col gap-3 rounded-[22px] border border-gray-200/70 bg-[#FCFCFC] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.96)] sm:flex-row sm:items-center sm:justify-between">
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => handleVisualReviewNavigation('prev')}
                                disabled={!canNavigateToPreviousReview}
                                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-700 transition-colors hover:border-gray-300 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                              >
                                <ChevronLeft className="h-4 w-4" />
                              </button>
                              <span className="inline-flex min-w-[72px] items-center justify-center rounded-full border border-gray-200 bg-white px-3 py-2 text-xs font-semibold text-gray-600">
                                {visualReviewPositionLabel}
                              </span>
                              <button
                                type="button"
                                onClick={() => handleVisualReviewNavigation('next')}
                                disabled={!canNavigateToNextReview}
                                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-gray-200 bg-white text-gray-700 transition-colors hover:border-gray-300 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                              >
                                <ChevronRight className="h-4 w-4" />
                              </button>
                            </div>
                            <p className="text-sm text-gray-500">
                              {isViewingVisualReviewHistory
                                ? `当前查看 @${effectiveSelectedVisualReview?.username || '未知对象'} 的已完成结果`
                                : (hasRunningLiveReview && activeLiveReviewSnapshot?.username
                                  ? `当前实时对象 @${activeLiveReviewSnapshot.username}`
                                  : '视觉复核启动后，这里会优先展示实时对象。')}
                            </p>
                          </div>

                          <div className="mt-5 grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
                            <div className="group/preview relative">
                              <button
                                type="button"
                                onClick={() => effectiveVisualReviewCollageUrl && setVisualPreviewModal(effectiveVisualReviewCollageUrl)}
                                className={`block w-full text-left ${effectiveVisualReviewCollageUrl ? 'cursor-zoom-in' : 'cursor-default'}`}
                              >
                                <div className="relative aspect-square overflow-hidden rounded-[22px] border border-gray-200/80 bg-[#F6F6F6] shadow-[inset_0_1px_0_rgba(255,255,255,0.95)] transition-[transform,box-shadow,border-color] duration-300 hover:-translate-y-0.5 hover:border-gray-300 hover:shadow-[0_16px_36px_rgba(15,23,42,0.10)]">
                                  {effectiveVisualReviewCollageUrl ? (
                                    <img
                                      src={effectiveVisualReviewCollageUrl}
                                      alt={effectiveSelectedVisualReview?.username ? `${effectiveSelectedVisualReview.username} 九宫格预览` : '九宫格预览'}
                                      className="h-full w-full object-cover"
                                    />
                                  ) : (
                                    <div className="flex h-full w-full items-center justify-center px-6 text-center text-sm leading-6 text-gray-400">
                                      视觉复核开始后，当前选中的九宫格会显示在这里。
                                    </div>
                                  )}
                                  {effectiveVisualReviewCollageUrl && (
                                    <>
                                      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-gray-900/8 via-transparent to-transparent" />
                                      <div className="pointer-events-none absolute bottom-3 left-3 rounded-full border border-white/80 bg-white/90 px-3 py-1.5 text-[11px] font-medium text-gray-700 shadow-[0_6px_18px_rgba(15,23,42,0.10)]">
                                        悬停放大 · 点击查看
                                      </div>
                                    </>
                                  )}
                                </div>
                              </button>

                              {effectiveVisualReviewCollageUrl && (
                                <div className="pointer-events-none absolute left-[calc(100%+18px)] top-0 z-30 hidden w-[320px] rounded-[26px] border border-gray-200/80 bg-white p-3 opacity-0 shadow-[0_20px_60px_rgba(15,23,42,0.12)] transition duration-200 xl:block xl:group-hover/preview:opacity-100">
                                  <img
                                    src={effectiveVisualReviewCollageUrl}
                                    alt="九宫格放大预览"
                                    className="aspect-square w-full rounded-[20px] object-cover"
                                  />
                                </div>
                              )}

                              {effectiveVisualReviewPreviewUrls.length > 1 && (
                                <div className="mt-3 grid grid-cols-2 gap-2">
                                  {effectiveVisualReviewPreviewUrls.map((previewUrl, previewIndex) => {
                                    const isReviewedPreview = previewIndex < effectiveVisualReviewedCollageCount;
                                    const previewLabel = isReviewedPreview
                                      ? `九宫格 ${previewIndex + 1}`
                                      : `九宫格 ${previewIndex + 1} · 保留预览`;
                                    return (
                                      <button
                                        key={`${previewUrl}-${previewIndex}`}
                                        type="button"
                                        onClick={() => setVisualPreviewModal(previewUrl)}
                                        className="overflow-hidden rounded-[18px] border border-gray-200/80 bg-white text-left shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition hover:-translate-y-0.5 hover:border-gray-300"
                                      >
                                        <img
                                          src={previewUrl}
                                          alt={previewLabel}
                                          className="aspect-square w-full object-cover"
                                        />
                                        <div className={`border-t px-3 py-2 text-[11px] font-medium ${
                                          isReviewedPreview
                                            ? 'border-gray-100 text-gray-500'
                                            : 'border-amber-100 bg-amber-50/80 text-amber-700'
                                        }`}>
                                          {previewLabel}
                                        </div>
                                      </button>
                                    );
                                  })}
                                </div>
                              )}
                            </div>

                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700">
                                  {formatLiveReviewStep(effectiveSelectedVisualReview?.step)}
                                </span>
                                {showVisualCoverProgressSummary ? (
                                  <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700">
                                    封面 {effectiveVisualCoverLoadedCount}/{effectiveVisualCoverRequestedCount}
                                  </span>
                                ) : typeof effectiveSelectedVisualReview?.coverCount === 'number' && (
                                  <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700">
                                    封面 {effectiveSelectedVisualReview.coverCount}
                                  </span>
                                )}
                                {typeof effectiveVisualCoverCurrentTotal === 'number' && effectiveVisualCoverCurrentTotal > 0 && typeof effectiveVisualCoverCurrentIndex === 'number' && (
                                  <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700">
                                    进度 {effectiveVisualCoverCurrentIndex}/{effectiveVisualCoverCurrentTotal}
                                  </span>
                                )}
                                {effectiveVisualCoverFailedCount > 0 && (
                                  <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">
                                    失败 {effectiveVisualCoverFailedCount}
                                  </span>
                                )}
                                {effectiveSelectedVisualReview?.decision && (
                                  <span className={`inline-flex items-center rounded-full border px-3 py-1.5 text-xs font-medium ${
                                    effectiveSelectedVisualReview.decision === 'Reject'
                                      ? 'border-rose-200 bg-rose-50 text-rose-700'
                                      : effectiveSelectedVisualReview.decision === 'Error'
                                        ? 'border-amber-200 bg-amber-50 text-amber-700'
                                        : 'border-emerald-200 bg-emerald-50 text-emerald-700'
                                  }`}>
                                    {effectiveSelectedVisualReview.decision}
                                  </span>
                                )}
                                {effectiveVisualReviewCollageCount > 0 && (
                                  <span className="inline-flex items-center rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600">
                                    九宫格 {effectiveVisualReviewCollageCount}{effectiveVisualReviewTargetCollageCount ? ` / ${effectiveVisualReviewTargetCollageCount}` : ''}
                                  </span>
                                )}
                                {effectiveVisualReviewedCollageCount > 0 && effectiveVisualReviewedCollageCount !== effectiveVisualReviewCollageCount && (
                                  <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700">
                                    实际送审 {effectiveVisualReviewedCollageCount}
                                  </span>
                                )}
                                {effectiveVisualUnusedCollageCount > 0 && (
                                  <span className="inline-flex items-center rounded-full border border-amber-200 bg-white px-3 py-1.5 text-xs font-medium text-amber-700">
                                    保留预览 {effectiveVisualUnusedCollageCount}
                                  </span>
                                )}
                                {effectiveVisualCollageErrorCount > 0 && (
                                  <span className="inline-flex items-center rounded-full border border-rose-200 bg-rose-50 px-3 py-1.5 text-xs font-medium text-rose-700">
                                    拼图失败 {effectiveVisualCollageErrorCount}
                                  </span>
                                )}
                                {effectiveVisualAppliedMode && (
                                  <span className="inline-flex items-center rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600">
                                    实际模式 {effectiveVisualAppliedMode === VISUAL_REVIEW_MODE_SIMPLE ? '简单' : '加强'}
                                  </span>
                                )}
                                {effectiveVisualRequestedMode && (
                                  <span className="inline-flex items-center rounded-full border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-500">
                                    请求 {effectiveVisualRequestedMode === VISUAL_REVIEW_MODE_SIMPLE ? '简单' : effectiveVisualRequestedMode === VISUAL_REVIEW_MODE_ENHANCED ? '加强' : '自动推荐'}
                                  </span>
                                )}
                              </div>

                              {showVisualCoverProgressSummary && (
                                <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-500">
                                  <span className="inline-flex items-center rounded-full border border-gray-200 bg-white px-3 py-1">
                                    封面加载 {effectiveVisualCoverCurrentIndex || effectiveVisualCoverRequestedCount}/{effectiveVisualCoverCurrentTotal || effectiveVisualCoverRequestedCount}
                                  </span>
                                  <span className="inline-flex items-center rounded-full border border-gray-200 bg-white px-3 py-1">
                                    成功 {effectiveVisualCoverLoadedCount} · 失败 {effectiveVisualCoverFailedCount}
                                  </span>
                                  {typeof effectiveSelectedVisualReview?.minRequiredCoverCount === 'number' && (
                                    <span className="inline-flex items-center rounded-full border border-gray-200 bg-white px-3 py-1">
                                      至少 {effectiveSelectedVisualReview.minRequiredCoverCount} 张可继续
                                    </span>
                                  )}
                                </div>
                              )}

                              {(effectiveVisualDowngradeReason || effectiveVisualRecommendedMode || effectiveVisualUnusedCollageCount > 0) && (
                                <div className="mt-3 space-y-2">
                                  {effectiveVisualRecommendedMode && (
                                    <div className="rounded-2xl border border-sky-200/70 bg-sky-50/80 px-4 py-3 text-sm leading-6 text-sky-800">
                                      系统建议模式：{effectiveVisualRecommendedMode === VISUAL_REVIEW_MODE_SIMPLE ? '简单' : '加强'}
                                    </div>
                                  )}
                                  {effectiveVisualUnusedCollageCount > 0 && (
                                    <div className="rounded-2xl border border-amber-200/70 bg-amber-50/80 px-4 py-3 text-sm leading-6 text-amber-800">
                                      当前共生成 {effectiveVisualReviewCollageCount} 张九宫格，其中 {effectiveVisualReviewedCollageCount} 张已送审，其余 {effectiveVisualUnusedCollageCount} 张仅保留给人工核对。
                                    </div>
                                  )}
                                  {effectiveVisualDowngradeReason && (
                                    <div className="rounded-2xl border border-amber-200/70 bg-amber-50/80 px-4 py-3 text-sm leading-6 text-amber-800">
                                      {effectiveVisualDowngradeReason}
                                    </div>
                                  )}
                                </div>
                              )}

                              <div className="mt-4 rounded-[22px] border border-gray-200/70 bg-[#FCFCFC] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.96)]">
                                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                  <div>
                                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Reasoning Log</p>
                                    <p className="mt-1 text-sm font-medium text-gray-700">
                                      {effectiveSelectedVisualReview?.username
                                        ? (isViewingVisualReviewHistory
                                          ? `当前查看 @${effectiveSelectedVisualReview.username}`
                                          : `当前正在审阅 @${effectiveSelectedVisualReview.username}`)
                                        : (visualLoading ? '视觉复核已启动，等待返回首个九宫格。' : '开始视觉复核后，这里会显示当前博主的推理日志。')}
                                    </p>
                                  </div>
                                  <span className="inline-flex w-fit items-center rounded-full border border-gray-200 bg-white px-3 py-1 text-xs font-medium text-gray-500">
                                    {effectiveVisualReviewLogs.length} 条日志
                                  </span>
                                </div>

                                <div className="mt-4 max-h-[220px] space-y-2 overflow-y-auto pr-1">
                                  {effectiveVisualReviewLogs.length > 0 ? (
                                    <AnimatePresence initial={false}>
                                      {effectiveVisualReviewLogs.map((log) => (
                                        <motion.div
                                          key={log.id}
                                          initial={{ opacity: 0, y: 8 }}
                                          animate={{ opacity: 1, y: 0 }}
                                          exit={{ opacity: 0, y: -8 }}
                                          className={`rounded-2xl border px-4 py-3 text-sm leading-6 shadow-[0_1px_2px_rgba(15,23,42,0.03)] ${getLiveReviewToneClassName(log.tone)}`}
                                        >
                                          {log.text}
                                        </motion.div>
                                      ))}
                                    </AnimatePresence>
                                  ) : (
                                    <div className="rounded-2xl border border-dashed border-gray-200/80 bg-white/90 px-4 py-8 text-center text-sm text-gray-500">
                                      当前还没有可显示的日志。视觉复核启动后，会在这里逐句刷新。
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        </motion.div>

                        <motion.div
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          className="rounded-[24px] border border-gray-200/70 bg-white p-5 shadow-[0_1px_3px_rgba(15,23,42,0.04),0_18px_42px_rgba(15,23,42,0.05)]"
                        >
                          <div className="flex items-start justify-between gap-4">
                            <div>
                              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Review Queue</p>
                              <h4 className="mt-2 text-lg font-semibold tracking-[-0.03em] text-gray-900">视觉复核状态</h4>
                              <p className="mt-2 text-sm leading-6 text-gray-500">
                                已完成列表支持点选跳转，实时对象单独保留一个入口，不会抢走你正在看的历史项。
                              </p>
                            </div>
                            <span className="inline-flex items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700">
                              {visualProgress.done} / {visualProgress.total || '—'}
                            </span>
                          </div>

                          <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-gray-100">
                            <motion.div
                              className="h-full bg-gray-900"
                              initial={{ width: 0 }}
                              animate={{ width: `${visualReviewProgressPercent}%` }}
                            />
                          </div>

                          <div className="mt-5 grid gap-3 sm:grid-cols-3">
                            <div className="rounded-2xl border border-gray-200/80 bg-[#FCFCFC] px-4 py-4">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-400">Passed</p>
                              <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-emerald-600">{visualPassedCount}</p>
                            </div>
                            <div className="rounded-2xl border border-gray-200/80 bg-[#FCFCFC] px-4 py-4">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-400">Rejected</p>
                              <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-rose-600">{visualRejectedCount}</p>
                            </div>
                            <div className="rounded-2xl border border-gray-200/80 bg-[#FCFCFC] px-4 py-4">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-gray-400">Failed</p>
                              <p className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-amber-600">{visualFailedCount}</p>
                            </div>
                          </div>

                          <div className="mt-5">
                            {hasRunningLiveReview && activeLiveReviewSnapshot && (
                              <button
                                type="button"
                                onClick={handleReturnToLiveReview}
                                className={`mb-3 flex w-full items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left text-sm transition-colors ${
                                  visualReviewSelection.mode === 'live'
                                    ? 'border-gray-900 bg-gray-900 text-white'
                                    : 'border-gray-200/80 bg-[#FCFCFC] text-gray-700 hover:border-gray-300 hover:bg-white'
                                }`}
                              >
                                <div>
                                  <p className={`text-[11px] font-semibold uppercase tracking-[0.16em] ${visualReviewSelection.mode === 'live' ? 'text-gray-200' : 'text-gray-400'}`}>
                                    Live Review
                                  </p>
                                  <p className="mt-1 font-semibold">
                                    @{activeLiveReviewSnapshot.username}
                                  </p>
                                </div>
                                <span className={`rounded-full px-3 py-1 text-xs font-medium ${
                                  visualReviewSelection.mode === 'live'
                                    ? 'bg-white/12 text-white'
                                    : 'border border-gray-200 bg-white text-gray-600'
                                }`}>
                                  {formatLiveReviewStep(activeLiveReviewSnapshot.step)}
                                </span>
                              </button>
                            )}

                            <div className="mb-3 flex items-center justify-between gap-3">
                              <h5 className="text-sm font-semibold text-gray-900">已完成复核</h5>
                              <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-medium text-gray-500">
                                {visualReviewHistory.length} 条
                              </span>
                            </div>

                            {visualReviewHistory.length > 0 ? (
                              <ul className="max-h-[280px] space-y-3 overflow-y-auto pr-1">
                                <AnimatePresence initial={false}>
                                  {visualReviewHistory.map((item, index) => {
                                      const isSuccess = item.success !== false && item.decision !== 'Reject';
                                      const isSelected = visualReviewSelection.mode === 'history'
                                        && effectiveSelectedVisualReview?.key === item.key;
                                      const outcomeLabel = formatVisualReviewOutcomeLabel(item);
                                      return (
                                        <motion.li
                                          key={`${item.key}-visual`}
                                          initial={{ opacity: 0, y: 10, scale: 0.98 }}
                                          animate={{ opacity: 1, y: 0, scale: 1 }}
                                          exit={{ opacity: 0, y: -8, scale: 0.98 }}
                                          className="list-none"
                                        >
                                          <button
                                            type="button"
                                            onClick={() => selectVisualReviewHistoryByIndex(index)}
                                            className={`flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left text-sm transition-colors ${
                                              isSelected
                                                ? 'border-gray-900 bg-gray-900 text-white'
                                                : 'border-gray-200/70 bg-[#FCFCFC] text-gray-700 hover:border-gray-300 hover:bg-white'
                                            }`}
                                          >
                                            {isSuccess
                                              ? <CheckCircle className={`h-5 w-5 shrink-0 ${isSelected ? 'text-emerald-300' : 'text-emerald-500'}`} />
                                              : <XCircle className={`h-5 w-5 shrink-0 ${isSelected ? 'text-rose-300' : 'text-rose-500'}`} />}
                                            <div className="min-w-0">
                                              <div className="flex flex-wrap items-center gap-2">
                                                <span className={`font-semibold ${isSelected ? 'text-white' : 'text-gray-900'}`}>{item.username}</span>
                                                <span className={`font-medium ${
                                                  isSelected
                                                    ? 'text-gray-200'
                                                    : (isSuccess ? 'text-emerald-600' : 'text-rose-600')
                                                }`}>
                                                  {outcomeLabel}
                                                </span>
                                              </div>
                                              {formatVisualReviewSummary(item) && (
                                                <p className={`mt-2 ${isSelected ? 'text-gray-200' : 'text-gray-600'}`}>
                                                  {formatVisualReviewSummary(item)}
                                                </p>
                                              )}
                                            </div>
                                          </button>
                                        </motion.li>
                                      );
                                    })}
                                </AnimatePresence>
                              </ul>
                            ) : (
                              <div className="rounded-2xl border border-dashed border-gray-200/80 bg-gray-50/70 px-4 py-10 text-center text-sm text-gray-500">
                                视觉复核开始后，已完成的结果会实时出现在这里。
                              </div>
                            )}
                          </div>
                        </motion.div>
                      </div>
                    ) : (
                      <div className="rounded-[24px] border border-dashed border-gray-200/80 bg-gray-50/70 px-6 py-12 text-center text-sm text-gray-500">
                        视觉复核 desk 会在启动任务或载入历史结果后显示在这里。
                      </div>
                    )}
                  </div>
                )}

                {activeResultTab === 'export-handoff' && (
                  <div className="mt-6 space-y-4">
                    {exportActionGroups.map((group) => (
                      <div key={group.key} className="rounded-[24px] border border-gray-200/80 bg-white px-4 py-4 shadow-[0_1px_2px_rgba(15,23,42,0.03)]">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">{group.eyebrow}</p>
                        <div className="mt-2 flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                          <div>
                            <h4 className="text-base font-semibold text-gray-900">{group.title}</h4>
                            <p className="mt-1 text-sm leading-6 text-gray-500">{group.description}</p>
                          </div>
                        </div>
                        <div className="mt-4 grid gap-3">
                          {group.actions.map((action) => (
                            <div
                              key={action.key}
                              className={`rounded-2xl border px-4 py-4 ${
                                action.enabled
                                  ? 'border-gray-200/80 bg-gray-50/80'
                                  : 'border-gray-200/70 bg-gray-50/40'
                              }`}
                            >
                              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                                <div className="min-w-0">
                                  <p className="text-sm font-semibold text-gray-900">{action.label}</p>
                                  <p className="mt-1 text-sm leading-6 text-gray-500">{action.hint}</p>
                                </div>
                                <button
                                  type="button"
                                  onClick={action.onClick}
                                  disabled={!action.enabled}
                                  className={`inline-flex shrink-0 items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold transition-[transform,box-shadow,border-color,background-color] duration-200 ${
                                    action.enabled
                                      ? 'cursor-pointer border border-gray-200 bg-white text-gray-700 hover:-translate-y-px hover:border-gray-300 hover:shadow-[0_12px_24px_rgba(15,23,42,0.07)]'
                                      : 'cursor-not-allowed border border-gray-200 bg-white/70 text-gray-400'
                                  }`}
                                >
                                  {action.busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                                  导出
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}

                    <div className="rounded-[24px] border border-gray-200/70 bg-white p-5 shadow-[0_1px_3px_rgba(15,23,42,0.04)]">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Run Snapshot</p>
                      <div className="mt-4 space-y-3 text-sm text-gray-600">
                        <div className="flex items-center justify-between gap-4">
                          <span>返回平台</span>
                          <span className="font-semibold text-gray-900">{activeResultPlatform}</span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>结果状态</span>
                          <span className="font-semibold text-gray-900">
                            {scrapeRunning ? (result.is_partial ? '部分结果' : '显示上次结果') : (result.cached ? '缓存结果' : '实时结果')}
                          </span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>博主卡片</span>
                          <span className="font-semibold text-gray-900">{resultProfileReviews.length}</span>
                        </div>
                        <div className="flex items-center justify-between gap-4">
                          <span>抓取记录</span>
                          <span className="font-semibold text-gray-900">{rawRecordCount}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {visualPreviewModal && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/45 px-5 py-8 backdrop-blur-sm"
              onClick={() => setVisualPreviewModal(null)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.96, y: 16 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.98, y: 8 }}
                transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                className="w-full max-w-xl rounded-[28px] border border-white/60 bg-white p-4 shadow-[0_30px_90px_rgba(15,23,42,0.22)]"
                onClick={(event) => event.stopPropagation()}
              >
                <div className="mb-3 flex items-center justify-between gap-4">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gray-400">Collage Preview</p>
                    <p className="mt-1 text-sm font-medium text-gray-700">九宫格放大预览</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setVisualPreviewModal(null)}
                    className="inline-flex cursor-pointer items-center rounded-full border border-gray-200 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:border-gray-300 hover:bg-white"
                  >
                    关闭
                  </button>
                </div>
                <img
                  src={visualPreviewModal}
                  alt="九宫格放大预览"
                  className="aspect-square w-full rounded-[22px] object-cover"
                />
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );

}

export default App;
