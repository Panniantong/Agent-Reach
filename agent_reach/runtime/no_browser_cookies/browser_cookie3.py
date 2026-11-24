"""Stand-in for browser-cookie3 on bili-cli's PYTHONPATH (see sessions.session_env).

Agent Reach never reads cookies from the user's own browsers. bili-cli treats a
failed import as "not installed" and keeps using its saved Agent Reach login.
"""

raise ImportError("Agent Reach does not let tools read the user's own browser cookies")
