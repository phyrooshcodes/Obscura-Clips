import json
import re

log_path = "/home/qwen/.gemini/antigravity-cli/brain/5470a5f6-37c6-4947-83bc-be2e3dc63dd3/.system_generated/logs/transcript_full.jsonl"

with open(log_path, "r", encoding="utf-8") as f:
    for line in f:
        try:
            step = json.loads(line)
            idx = step.get("step_index")
            if idx == 42:
                content = step.get("content", "")
                # Print lines from 1750 to 1785
                lines = content.splitlines()
                for l in lines[-35:]:
                    print(l)
        except Exception as e:
            pass
