import json
import os
import sys
import subprocess
import time
from datetime import datetime, timezone

# Path to the Apify auth file
AUTH_FILE_PATH = os.path.expanduser("~/.apify/auth.json")
STATE_FILE_PATH = os.path.expanduser("~/.apify/token_manager_state.json")

# List of available backup tokens
BACKUP_TOKENS = [
    # Add your Apify API tokens here
    # e.g. "apify_api_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
]

class TokenManager:
    def __init__(self):
        self.auth_file = AUTH_FILE_PATH
        self.state_file = STATE_FILE_PATH
        self.backup_tokens = BACKUP_TOKENS

    def _now_iso(self):
        return datetime.now(timezone.utc).isoformat()

    def _mask_token(self, token):
        if not token:
            return ""
        return f"...{token[-5:]}"

    def load_state(self):
        try:
            if not os.path.exists(self.state_file):
                return {"tokens": {}}
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"tokens": {}}
            if not isinstance(data.get("tokens"), dict):
                data["tokens"] = {}
            return data
        except Exception as e:
            print(f"[TokenManager] Error reading state file: {e}")
            return {"tokens": {}}

    def save_state(self, state):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            return True
        except Exception as e:
            print(f"[TokenManager] Failed to write state file: {e}")
            return False

    def mark_token_event(self, token, result=None, rotated_from=None, count_as_use=True):
        if not token:
            return

        state = self.load_state()
        tokens = state.setdefault("tokens", {})
        token_state = tokens.get(token, {})
        previous_use_count = int(token_state.get("use_count", 0) or 0)

        token_state["masked"] = self._mask_token(token)
        if count_as_use:
            token_state["used_before"] = True
            token_state["use_count"] = previous_use_count + 1
            token_state["last_used_at"] = self._now_iso()
            if "first_used_at" not in token_state:
                token_state["first_used_at"] = token_state["last_used_at"]
        else:
            token_state.setdefault("used_before", False)
            token_state.setdefault("use_count", previous_use_count)
        if result:
            token_state["last_result"] = result
        if rotated_from:
            token_state["rotated_from"] = self._mask_token(rotated_from)

        tokens[token] = token_state
        state["current_token"] = token
        state["current_token_masked"] = self._mask_token(token)
        self.save_state(state)

    def print_status(self):
        current_token = self.get_current_token()
        state = self.load_state()
        tokens = state.get("tokens", {})

        print("[TokenManager] Current auth token:", self._mask_token(current_token))
        print("[TokenManager] Known token usage:")
        for token in self.backup_tokens:
            token_state = tokens.get(token, {})
            print(json.dumps({
                "token": self._mask_token(token),
                "is_current": token == current_token,
                "used_before": bool(token_state.get("used_before", False)),
                "use_count": int(token_state.get("use_count", 0) or 0),
                "first_used_at": token_state.get("first_used_at"),
                "last_used_at": token_state.get("last_used_at"),
                "last_result": token_state.get("last_result"),
                "rotated_from": token_state.get("rotated_from"),
            }, ensure_ascii=False))

    def get_current_token(self):
        """Reads the current token from the auth file."""
        try:
            if not os.path.exists(self.auth_file):
                print(f"[TokenManager] Error: Auth file not found at {self.auth_file}")
                return None
                
            with open(self.auth_file, 'r') as f:
                data = json.load(f)
                return data.get('token')
        except Exception as e:
            print(f"[TokenManager] Error reading auth file: {e}")
            return None

    def update_token(self, new_token):
        """Updates the token in the auth file."""
        try:
            with open(self.auth_file, 'r') as f:
                data = json.load(f)
            
            old_token = data.get('token')
            data['token'] = new_token
            
            # Using tab indentation to match original file style
            with open(self.auth_file, 'w') as f:
                json.dump(data, f, indent='\t')

            print(f"[TokenManager] Token rotated: {self._mask_token(old_token)} -> {self._mask_token(new_token)}")
            self.mark_token_event(new_token, result="rotated_in", rotated_from=old_token, count_as_use=False)
            return True
        except Exception as e:
            print(f"[TokenManager] Failed to update token: {e}")
            return False

    def rotate_token(self):
        """Rotates to the next available token."""
        current_token = self.get_current_token()
        if not current_token:
            print("[TokenManager] No current token found, setting to first backup.")
            self.update_token(self.backup_tokens[0])
            return self.backup_tokens[0]
        
        # Determine the next token
        next_token = None
        if current_token in self.backup_tokens:
            idx = self.backup_tokens.index(current_token)
            # Move to next, loop back to start if at end
            next_idx = (idx + 1) % len(self.backup_tokens)
            next_token = self.backup_tokens[next_idx]
        else:
            # If current is not in our backup list (e.g. the original one), start with the first backup
            next_token = self.backup_tokens[0]
        
        self.update_token(next_token)
        return next_token

    def run_command(self, command, max_retries=3):
        """
        Runs a shell command. If it fails, rotates token and retries.
        """
        retries = 0
        while retries <= max_retries:
            print(f"\n[TokenManager] Running command (Attempt {retries + 1}/{max_retries + 1}): {command}")
            current_token = self.get_current_token()
            try:
                # Run the command
                process = subprocess.run(command, shell=True)
                
                if process.returncode == 0:
                    self.mark_token_event(current_token, result="success")
                    print("[TokenManager] Command executed successfully.")
                    return True
                else:
                    self.mark_token_event(current_token, result=f"exit_code_{process.returncode}")
                    print(f"[TokenManager] Command failed with exit code {process.returncode}.")
                    
                    if retries < max_retries:
                        print("[TokenManager] Possible API limit reached. Rotating token and retrying...")
                        self.rotate_token()
                        retries += 1
                        time.sleep(2) # Wait a bit before retry
                    else:
                        print("[TokenManager] Max retries reached. Execution failed.")
                        return False
                        
            except Exception as e:
                print(f"[TokenManager] Execution error: {e}")
                return False

if __name__ == "__main__":
    manager = TokenManager()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python apify_token_manager.py rotate            # Manually rotate token")
        print("  python apify_token_manager.py status            # Show token usage state")
        print("  python apify_token_manager.py <command>         # Run command with auto-rotation")
        print("Example:")
        print("  python apify_token_manager.py apify actor run my-actor")
    elif sys.argv[1] == "rotate":
        manager.rotate_token()
    elif sys.argv[1] == "status":
        manager.print_status()
    else:
        command = " ".join(sys.argv[1:])
        manager.run_command(command)
