"""
Sparkbot skill: linear_jira

Issue tracker integration for Linear and Jira.

Linear tools (requires LINEAR_API_KEY):
  linear_list_issues(team="", state="", assignee="", limit=20)
  linear_create_issue(title, description="", team="", priority=0)
  linear_update_issue(issue_id, state="", priority=None, comment="")

Jira tools (requires JIRA_BASE_URL + JIRA_EMAIL + JIRA_API_TOKEN):
  jira_list_issues(project="", assignee="me", status="", limit=20)
  jira_create_issue(project, summary, description="", issue_type="Task", priority="Medium")
  jira_add_comment(issue_key, comment)

Env vars:
  LINEAR_API_KEY      — from linear.app → Settings → API
  JIRA_BASE_URL       — e.g. https://yourco.atlassian.net
  JIRA_EMAIL          — your Atlassian account email
  JIRA_API_TOKEN      — from id.atlassian.com → Security → API tokens
"""
from __future__ import annotations

import os

import httpx

_LINEAR_KEY  = os.getenv("LINEAR_API_KEY", "").strip()
_JIRA_BASE   = os.getenv("JIRA_BASE_URL", "").strip().rstrip("/")
_JIRA_EMAIL  = os.getenv("JIRA_EMAIL", "").strip()
_JIRA_TOKEN  = os.getenv("JIRA_API_TOKEN", "").strip()

_LINEAR_URL  = "https://api.linear.app/graphql"

# ── Linear helpers ─────────────────────────────────────────────────────────────

async def _linear_gql(query: str, variables: dict | None = None) -> dict:
    if not _LINEAR_KEY:
        return {"error": "LINEAR_API_KEY not configured."}
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            _LINEAR_URL,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": _LINEAR_KEY, "Content-Type": "application/json"},
        )
    if r.status_code != 200:
        return {"error": f"Linear API error {r.status_code}: {r.text[:300]}"}
    return r.json()


async def _linear_list_issues(args: dict, **_) -> str:
    team    = (args.get("team") or "").strip()
    state   = (args.get("state") or "").strip()
    assignee = (args.get("assignee") or "").strip()
    limit   = max(1, min(int(args.get("limit") or 20), 50))

    filters: list[str] = []
    if state:
        filters.append(f'state: {{name: {{eq: "{state}"}}}},')
    if team:
        filters.append(f'team: {{name: {{containsIgnoreCase: "{team}"}}}},')
    filter_block = "filter: {" + " ".join(filters) + "}" if filters else ""

    query = f"""
    query {{
      issues({filter_block} first: {limit} orderBy: updatedAt) {{
        nodes {{
          identifier title state {{ name }} priority assignee {{ name }} url updatedAt
        }}
      }}
    }}
    """
    data = await _linear_gql(query)
    if "error" in data:
        return data["error"]
    issues = data.get("data", {}).get("issues", {}).get("nodes", [])
    if not issues:
        return "No Linear issues found matching those filters."
    lines = [f"**Linear Issues ({len(issues)})**", ""]
    for i in issues:
        pri = ["", "🔴", "🟠", "🟡", "🔵"].get(i.get("priority", 0), "")
        assignee_name = (i.get("assignee") or {}).get("name", "—")
        lines.append(
            f"**{i['identifier']}** {pri} {i['title']}\n"
            f"  State: {i.get('state',{}).get('name','?')} · Assignee: {assignee_name} · {i['url']}"
        )
    return "\n".join(lines)


async def _linear_create_issue(args: dict, **_) -> str:
    title = (args.get("title") or "").strip()
    if not title:
        return "Error: title is required."
    description = (args.get("description") or "").strip()
    priority = int(args.get("priority") or 0)
    team_name = (args.get("team") or "").strip()

    # Get team ID first if specified
    team_id_gql = ""
    if team_name:
        team_data = await _linear_gql(f'query {{ teams(filter: {{name: {{containsIgnoreCase: "{team_name}"}}}}) {{ nodes {{ id name }} }} }}')
        teams = team_data.get("data", {}).get("teams", {}).get("nodes", [])
        if teams:
            team_id_gql = f'teamId: "{teams[0]["id"]}"'

    mut = f"""
    mutation {{
      issueCreate(input: {{
        title: "{title}"
        description: "{description}"
        priority: {priority}
        {team_id_gql}
      }}) {{
        success issue {{ identifier url }}
      }}
    }}
    """
    data = await _linear_gql(mut)
    if "error" in data:
        return data["error"]
    result = data.get("data", {}).get("issueCreate", {})
    if result.get("success"):
        issue = result.get("issue", {})
        return f"✅ Created Linear issue **{issue.get('identifier')}**: {issue.get('url')}"
    return f"Failed to create issue: {data}"


async def _linear_update_issue(args: dict, **_) -> str:
    issue_id = (args.get("issue_id") or "").strip()
    if not issue_id:
        return "Error: issue_id is required."
    state   = (args.get("state") or "").strip()
    comment = (args.get("comment") or "").strip()

    results: list[str] = []

    if state:
        # Resolve state ID
        state_data = await _linear_gql(f'query {{ workflowStates(filter: {{name: {{eq: "{state}"}}}}) {{ nodes {{ id name }} }} }}')
        states = state_data.get("data", {}).get("workflowStates", {}).get("nodes", [])
        if states:
            sid = states[0]["id"]
            mut = f'mutation {{ issueUpdate(id: "{issue_id}", input: {{stateId: "{sid}"}}) {{ success }} }}'
            r = await _linear_gql(mut)
            results.append("State updated ✓" if r.get("data", {}).get("issueUpdate", {}).get("success") else f"State update failed: {r}")

    if comment:
        mut = f'mutation {{ commentCreate(input: {{issueId: "{issue_id}", body: "{comment}"}}) {{ success }} }}'
        r = await _linear_gql(mut)
        results.append("Comment added ✓" if r.get("data", {}).get("commentCreate", {}).get("success") else f"Comment failed: {r}")

    return "\n".join(results) if results else "Nothing to update."


# ── Jira helpers ───────────────────────────────────────────────────────────────

def _jira_auth():
    from httpx import BasicAuth
    return BasicAuth(_JIRA_EMAIL, _JIRA_TOKEN)


async def _jira_list_issues(args: dict, **_) -> str:
    if not (_JIRA_BASE and _JIRA_EMAIL and _JIRA_TOKEN):
        return "Jira not configured. Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN."
    project = (args.get("project") or "").strip()
    status  = (args.get("status") or "").strip()
    assignee = (args.get("assignee") or "me").strip()
    limit   = max(1, min(int(args.get("limit") or 20), 50))

    jql_parts: list[str] = []
    if project:
        jql_parts.append(f'project = "{project}"')
    if assignee == "me":
        jql_parts.append("assignee = currentUser()")
    elif assignee:
        jql_parts.append(f'assignee = "{assignee}"')
    if status:
        jql_parts.append(f'status = "{status}"')
    jql = " AND ".join(jql_parts) if jql_parts else "assignee = currentUser()"
    jql += " ORDER BY updated DESC"

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            f"{_JIRA_BASE}/rest/api/3/search",
            params={"jql": jql, "maxResults": limit, "fields": "summary,status,assignee,priority,issuetype"},
            auth=_jira_auth(),
        )
    if r.status_code != 200:
        return f"Jira error {r.status_code}: {r.text[:300]}"
    issues = r.json().get("issues", [])
    if not issues:
        return "No Jira issues found."
    lines = [f"**Jira Issues ({len(issues)})**", ""]
    for i in issues:
        f = i.get("fields", {})
        status_name = f.get("status", {}).get("name", "?")
        assignee_name = (f.get("assignee") or {}).get("displayName", "Unassigned")
        lines.append(
            f"**{i['key']}** {f.get('summary','')}\n"
            f"  {status_name} · {assignee_name} · {_JIRA_BASE}/browse/{i['key']}"
        )
    return "\n".join(lines)


async def _jira_create_issue(args: dict, **_) -> str:
    if not (_JIRA_BASE and _JIRA_EMAIL and _JIRA_TOKEN):
        return "Jira not configured."
    project = (args.get("project") or "").strip()
    summary = (args.get("summary") or "").strip()
    if not project or not summary:
        return "Error: project and summary are required."
    description = (args.get("description") or "").strip()
    issue_type = (args.get("issue_type") or "Task").strip()
    priority_name = (args.get("priority") or "Medium").strip()

    payload: dict = {
        "fields": {
            "project": {"key": project},
            "summary": summary,
            "issuetype": {"name": issue_type},
            "priority": {"name": priority_name},
        }
    }
    if description:
        payload["fields"]["description"] = {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}],
        }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{_JIRA_BASE}/rest/api/3/issue",
            json=payload,
            auth=_jira_auth(),
        )
    if r.status_code in (200, 201):
        key = r.json().get("key", "?")
        return f"✅ Created Jira issue **{key}**: {_JIRA_BASE}/browse/{key}"
    return f"Jira create error {r.status_code}: {r.text[:300]}"


async def _jira_add_comment(args: dict, **_) -> str:
    if not (_JIRA_BASE and _JIRA_EMAIL and _JIRA_TOKEN):
        return "Jira not configured."
    key     = (args.get("issue_key") or "").strip()
    comment = (args.get("comment") or "").strip()
    if not key or not comment:
        return "Error: issue_key and comment are required."
    payload = {
        "body": {
            "type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment}]}],
        }
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{_JIRA_BASE}/rest/api/3/issue/{key}/comment",
            json=payload,
            auth=_jira_auth(),
        )
    if r.status_code in (200, 201):
        return f"✅ Comment added to {key}."
    return f"Jira comment error {r.status_code}: {r.text[:300]}"


DEFINITIONS = [
    {"type": "function", "function": {"name": "linear_list_issues", "description": "List Linear issues. Filter by team, state, or assignee.", "parameters": {"type": "object", "properties": {"team": {"type": "string"}, "state": {"type": "string", "description": "e.g. 'In Progress', 'Todo', 'Done'"}, "assignee": {"type": "string"}, "limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "linear_create_issue", "description": "Create a new Linear issue.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "team": {"type": "string"}, "priority": {"type": "integer", "description": "0=none,1=urgent,2=high,3=medium,4=low"}}, "required": ["title"]}}},
    {"type": "function", "function": {"name": "linear_update_issue", "description": "Update a Linear issue state or add a comment.", "parameters": {"type": "object", "properties": {"issue_id": {"type": "string"}, "state": {"type": "string"}, "comment": {"type": "string"}}, "required": ["issue_id"]}}},
    {"type": "function", "function": {"name": "jira_list_issues", "description": "List Jira issues. Filter by project, status, or assignee.", "parameters": {"type": "object", "properties": {"project": {"type": "string"}, "assignee": {"type": "string", "description": "'me' for current user (default)"}, "status": {"type": "string"}, "limit": {"type": "integer"}}, "required": []}}},
    {"type": "function", "function": {"name": "jira_create_issue", "description": "Create a new Jira issue.", "parameters": {"type": "object", "properties": {"project": {"type": "string", "description": "Project key e.g. DEV"}, "summary": {"type": "string"}, "description": {"type": "string"}, "issue_type": {"type": "string", "description": "Task, Bug, Story, Epic (default Task)"}, "priority": {"type": "string", "description": "Highest, High, Medium, Low, Lowest"}}, "required": ["project", "summary"]}}},
    {"type": "function", "function": {"name": "jira_add_comment", "description": "Add a comment to a Jira issue.", "parameters": {"type": "object", "properties": {"issue_key": {"type": "string", "description": "e.g. DEV-123"}, "comment": {"type": "string"}}, "required": ["issue_key", "comment"]}}},
]

POLICIES = {
    "linear_list_issues":  {"scope": "read",  "resource": "workspace", "default_action": "allow",   "action_type": "read",       "high_risk": False, "requires_execution_gate": False},
    "linear_create_issue": {"scope": "write", "resource": "workspace", "default_action": "confirm",  "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "linear_update_issue": {"scope": "write", "resource": "workspace", "default_action": "confirm",  "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "jira_list_issues":    {"scope": "read",  "resource": "workspace", "default_action": "allow",   "action_type": "read",       "high_risk": False, "requires_execution_gate": False},
    "jira_create_issue":   {"scope": "write", "resource": "workspace", "default_action": "confirm",  "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "jira_add_comment":    {"scope": "write", "resource": "workspace", "default_action": "confirm",  "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
}

_EXECUTORS = {
    "linear_list_issues":  _linear_list_issues,
    "linear_create_issue": _linear_create_issue,
    "linear_update_issue": _linear_update_issue,
    "jira_list_issues":    _jira_list_issues,
    "jira_create_issue":   _jira_create_issue,
    "jira_add_comment":    _jira_add_comment,
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["linear_list_issues"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await _linear_list_issues(args)


def _wrap(fn):
    async def _e(args: dict, *, user_id=None, room_id=None, session=None) -> str:
        return await fn(args)
    return _e


def _register_extra(registry) -> None:
    for defn in DEFINITIONS:
        name = defn["function"]["name"]
        if name not in registry.executors:
            registry.definitions.append(defn)
            registry.policies[name] = POLICIES[name]
            registry.executors[name] = _wrap(_EXECUTORS[name])
