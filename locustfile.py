from locust import HttpUser, task, between
import json
import hmac
import hashlib

SECRET = "codesentinel2026secret"

class CodeSentinelUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def trigger_webhook(self):
        payload = {
            "action": "opened",
            "number": 3,
            "pull_request": {
                "number": 3,
                "head": {
                    "sha": "22252cbace9eed9ef44f1336f5c67aed6543738d"
                }
            },
            "repository": {
                "full_name": "akashagalave/test-repo"
            }
        }

        body = json.dumps(payload)

        signature = "sha256=" + hmac.new(
            SECRET.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request"
        }

        self.client.post("/webhook/github", data=body, headers=headers)