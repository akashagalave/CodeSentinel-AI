# locustfile.py
# Load test: 10 concurrent users each opening PRs
# Run: locust -f locustfile.py --users 10 --spawn-rate 2 --run-time 2m
# Or:  make load-test
# Open: http://localhost:8089 for web UI

import hashlib
import hmac
import json
import os
import time
from locust import HttpUser, task, between


WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "codesentinel2026mysecret")

# Sample PR diffs for testing
SAMPLE_DIFFS = [
    """diff --git a/src/auth.py b/src/auth.py
@@ -10,6 +10,15 @@ class AuthManager:
+    def authenticate(self, username: str, password: str):
+        query = f"SELECT * FROM users WHERE username = '{username}'"
+        user = self.db.execute(query).fetchone()
+        if user and user.password == password:
+            return user
+        return None""",

    """diff --git a/src/api.py b/src/api.py
@@ -5,4 +5,12 @@
+    def get_users(self, page: int):
+        users = []
+        for user_id in self.get_all_ids():
+            user = User.objects.get(id=user_id)
+            users.append(user)
+        return users""",

    """diff --git a/src/cache.py b/src/cache.py
@@ -1,3 +1,8 @@
+    def process_items(self, items: list):
+        result = ""
+        for item in items:
+            result = result + str(item) + ","
+        return result""",
]


def make_signature(payload: bytes, secret: str) -> str:
    """Create HMAC-SHA256 signature like GitHub does."""
    sig = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={sig}"


class CodeSentinelUser(HttpUser):
    """Simulates a developer opening a PR."""
    wait_time = between(1, 3)   # wait 1-3 seconds between tasks

    @task
    def open_pr(self):
        """Simulate GitHub sending a PR webhook."""
        import random

        diff = random.choice(SAMPLE_DIFFS)
        pr_number = random.randint(1, 1000)

        payload = {
            "action": "opened",
            "number": pr_number,
            "pull_request": {
                "head": {
                    "sha": f"abc{pr_number:04d}def",
                },
                "title": f"Test PR #{pr_number}",
            },
            "repository": {
                "full_name": "test-org/test-repo",
            },
        }

        # Add diff to payload (in real GitHub, we'd fetch it separately)
        # For load test, we inject it directly
        payload["_test_diff"] = diff

        body = json.dumps(payload).encode("utf-8")
        signature = make_signature(body, WEBHOOK_SECRET)

        start = time.time()
        response = self.client.post(
            "/webhook/github",
            data=body,
            headers={
                "Content-Type":          "application/json",
                "X-Hub-Signature-256":   signature,
                "X-GitHub-Event":        "pull_request",
            },
        )

        latency = (time.time() - start) * 1000

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "queued":
                # Gateway returned 200 fast — this is what we measure
                pass

    @task(weight=2)
    def health_check(self):
        """Occasional health checks."""
        self.client.get("/health")