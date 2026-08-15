"""GitHub repository enrichment for fetching verified star counts directly from GitHub REST API."""
import os
import re
from typing import Optional, Tuple
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.utils.logger import logger

class GitHubEnricher:
    """Enriches paper records with verified GitHub star counts from the GitHub API."""

    def __init__(self, crawler: Optional[BaseAsyncCrawler] = None):
        self.crawler = crawler or BaseAsyncCrawler()
        self.token = os.getenv("GITHUB_TOKEN")

    def parse_repo_owner_name(self, github_url: str) -> Optional[Tuple[str, str]]:
        """Extract (owner, repo) from GitHub URL."""
        if not github_url:
            return None
        match = re.search(r"github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)", github_url)
        if match:
            owner = match.group(1)
            repo = match.group(2).rstrip("/")
            if repo.endswith(".git"):
                repo = repo[:-4]
            return owner, repo
        return None

    async def get_star_count(self, github_url: str) -> Optional[int]:
        """Fetch stargazers_count for a GitHub repository directly from GitHub API."""
        owner_repo = self.parse_repo_owner_name(github_url)
        if not owner_repo:
            return None

        owner, repo = owner_repo
        api_url = f"https://api.github.com/repos/{owner}/{repo}"

        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        resp = await self.crawler.fetch(api_url, headers=headers)
        if resp.status_code == 200:
            try:
                import json
                data = json.loads(resp.text)
                stars = data.get("stargazers_count")
                if isinstance(stars, int):
                    logger.info(
                        f"Verified {stars} GitHub stars for {owner}/{repo}",
                        extra={"component": "GitHubEnricher", "url": github_url}
                    )
                    return stars
            except Exception as e:
                logger.warning(
                    f"Failed to parse GitHub API response for {owner}/{repo}: {e}",
                    extra={"component": "GitHubEnricher"}
                )
        else:
            logger.warning(
                f"GitHub API returned {resp.status_code} for {owner}/{repo}",
                extra={"component": "GitHubEnricher", "status_code": resp.status_code}
            )

        return None
