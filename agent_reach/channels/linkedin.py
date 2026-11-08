"""LinkedIn job actions through upstream OpenCLI and the shared Reach browser."""
import re
from urllib.parse import urlsplit

from agent_reach.runtime.result import BAD_INPUT, ReachError
from agent_reach.utils.url import host_matches

from ._opencli_site import OpenCLISiteChannel
from .base import Action, Param


class LinkedInChannel(OpenCLISiteChannel):
    name = site = "linkedin"
    description = "LinkedIn 职位搜索与详情"
    domains = ("linkedin.com",)
    login_hint = "linkedin.com"
    login_url = "https://www.linkedin.com/login"
    login_cookie = "li_at"
    level = "optional"
    actions = (
        Action("jobs", "Search LinkedIn jobs", (
            Param("query", "job keywords"), Param("location", "city or country", required=False),
            Param("limit", "max results", required=False, type=int, default=5)),
            (("opencli", "_jobs"),), live_test={"query": "python", "limit": 2}, timeout=120,
            public_web=("linkedin.com/jobs/view/",)),
        Action("read", "Read a LinkedIn job description", (Param("target", "full job URL"),),
               (("opencli", "_read"),), timeout=90, public_web=("linkedin.com/jobs/view/",)),
    )

    def _jobs(self, *, query, location, limit, timeout):
        args = ["search", query, "--limit", str(limit)]
        if location:
            args += ["--location", location]
        return self._opencli(args, timeout)[:limit]

    def _read(self, *, target, timeout):
        if not host_matches(str(target), "linkedin.com"):
            raise ReachError(BAD_INPUT, "Expected a linkedin.com job URL")
        return self._opencli(["job-detail", self._job_url(str(target))], timeout)[:1]

    @staticmethod
    def _job_url(target: str) -> str:
        if not host_matches(target, "linkedin.com"):
            raise ReachError(BAD_INPUT, "Expected a linkedin.com job URL")
        match = re.fullmatch(r"/jobs/view/(?:[^/]+-)?([0-9]+)/?", urlsplit(target).path)
        if not match:
            raise ReachError(BAD_INPUT, "Expected a LinkedIn /jobs/view/<job-id> URL")
        # Public indexes use regional hosts and title slugs; upstream accepts IDs.
        return "https://www.linkedin.com/jobs/view/" + match.group(1)

    def validate_params(self, action, params):
        if action == "read":
            params["target"] = self._job_url(str(params["target"]))
