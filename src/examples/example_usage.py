#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "webhooky @ git+https://github.com/Bullish-Design/webhooky.git",
#     "fastapi",
#     "uvicorn",
# ]
# ///
"""Example: GitHub webhook event handling with WebHooky."""
from __future__ import annotations

import asyncio
from typing import Dict, Any

from pydantic import field_validator

from webhooky import EventBus, WebhookEventBase, on_push, on_activity, on_create


# Define GitHub event classes
class GitHubPushEvent(WebhookEventBase):
    """GitHub push webhook event."""
    
    @field_validator('raw_data')
    @classmethod
    def validate_push_data(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        required_fields = ['ref', 'repository', 'commits']
        if not all(field in v for field in required_fields):
            raise ValueError(f"Missing required GitHub push fields: {required_fields}")
        return v
    
    @property
    def repository_name(self) -> str:
        return self.raw_data.get('repository', {}).get('name', 'unknown')
    
    @property
    def branch(self) -> str:
        ref = self.raw_data.get('ref', '')
        return ref.replace('refs/heads/', '') if ref.startswith('refs/heads/') else ref
    
    @property
    def commit_count(self) -> int:
        return len(self.raw_data.get('commits', []))
    
    @on_push()
    async def log_push(self):
        print(f"🚀 Push to {self.repository_name}/{self.branch}: {self.commit_count} commits")
    
    @on_activity('push')
    async def deploy_production(self):
        if self.branch == 'main' and self.commit_count > 0:
            print(f"🚀 Deploying {self.repository_name} to production")
            # Simulate deployment
            await asyncio.sleep(0.1)
            print(f"✅ Deployed {self.repository_name} successfully")


class GitHubIssueEvent(WebhookEventBase):
    """GitHub issue webhook event."""
    
    @classmethod
    def matches(cls, raw_data: Dict[str, Any], headers=None) -> bool:
        return (
            'action' in raw_data and
            'issue' in raw_data and
            raw_data['action'] in ['opened', 'closed', 'edited', 'labeled']
        )
    
    @property
    def issue_title(self) -> str:
        return self.raw_data.get('issue', {}).get('title', 'Untitled')
    
    @property
    def issue_number(self) -> int:
        return self.raw_data.get('issue', {}).get('number', 0)
    
    @property
    def action(self) -> str:
        return self.raw_data.get('action', '')
    
    @on_create()
    async def notify_new_issue(self):
        if self.action == 'opened':
            print(f"📋 New issue #{self.issue_number}: {self.issue_title}")
    
    @on_activity('closed')
    async def celebrate_closure(self):
        print(f"✅ Issue #{self.issue_number} closed: {self.issue_title}")
    
    @on_activity('labeled')
    async def handle_priority_label(self):
        labels = self.raw_data.get('issue', {}).get('labels', [])
        priority_labels = [l['name'] for l in labels if 'priority' in l.get('name', '').lower()]
        if priority_labels:
            print(f"🏷️  Priority label added to issue #{self.issue_number}: {priority_labels}")


class GitHubPullRequestEvent(WebhookEventBase):
    """GitHub pull request webhook event."""
    
    @field_validator('raw_data')
    @classmethod
    def validate_pr_data(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if 'pull_request' not in v or 'action' not in v:
            raise ValueError("Missing pull_request or action fields")
        return v
    
    @property
    def pr_title(self) -> str:
        return self.raw_data.get('pull_request', {}).get('title', 'Untitled PR')
    
    @property
    def pr_number(self) -> int:
        return self.raw_data.get('pull_request', {}).get('number', 0)
    
    @property
    def action(self) -> str:
        return self.raw_data.get('action', '')
    
    @on_create()
    async def review_requested(self):
        if self.action == 'opened':
            print(f"🔍 New PR #{self.pr_number} opened: {self.pr_title}")
            print("  → Requesting code review")
    
    @on_activity('closed')
    async def handle_merge(self):
        pr = self.raw_data.get('pull_request', {})
        if pr.get('merged', False):
            print(f"🎉 PR #{self.pr_number} merged: {self.pr_title}")
        else:
            print(f"❌ PR #{self.pr_number} closed without merge: {self.pr_title}")


# Example usage
async def main():
    # Create bus and register event classes
    bus = EventBus(timeout_seconds=10.0)
    bus.register_all(GitHubPushEvent, GitHubIssueEvent, GitHubPullRequestEvent)
    
    # Sample GitHub webhook payloads
    push_payload = {
        'ref': 'refs/heads/main',
        'repository': {'name': 'my-awesome-app', 'full_name': 'user/my-awesome-app'},
        'commits': [
            {'message': 'Fix critical bug', 'author': {'name': 'Developer'}},
            {'message': 'Update README', 'author': {'name': 'Developer'}}
        ],
        'pusher': {'name': 'developer'}
    }
    
    issue_payload = {
        'action': 'opened',
        'issue': {
            'number': 42,
            'title': 'Critical bug in payment system',
            'labels': [{'name': 'bug'}, {'name': 'priority-high'}]
        }
    }
    
    pr_payload = {
        'action': 'opened',
        'pull_request': {
            'number': 123,
            'title': 'Add user authentication',
            'merged': False
        }
    }
    
    # Process webhooks
    print("=== Processing GitHub Push Webhook ===")
    result1 = await bus.process_webhook(push_payload)
    print(f"Success: {result1.success}, Patterns: {result1.matched_patterns}")
    
    print("\n=== Processing GitHub Issue Webhook ===")
    result2 = await bus.process_webhook(issue_payload)
    print(f"Success: {result2.success}, Patterns: {result2.matched_patterns}")
    
    print("\n=== Processing GitHub PR Webhook ===")
    result3 = await bus.process_webhook(pr_payload)
    print(f"Success: {result3.success}, Patterns: {result3.matched_patterns}")
    
    print(f"\nRegistered classes: {bus.get_registered_classes()}")
    print(f"Bus stats: {bus.get_stats()}")


# FastAPI server example
def create_github_webhook_server():
    """Create FastAPI server for GitHub webhooks."""
    from webhooky import create_app
    from webhooky.config import create_config
    
    # Create bus and register GitHub events
    bus = EventBus(timeout_seconds=30.0)
    bus.register_all(GitHubPushEvent, GitHubIssueEvent, GitHubPullRequestEvent)
    
    # Create config and app
    config = create_config(
        timeout_seconds=30.0,
        api_prefix="/github",
        host="0.0.0.0",
        port=8000
    )
    
    app = create_app(bus, config)
    return app


if __name__ == '__main__':
    # Run the example
    asyncio.run(main())
    
    # Uncomment to run FastAPI server instead:
    # import uvicorn
    # app = create_github_webhook_server()
    # uvicorn.run(app, host="0.0.0.0", port=8000)
