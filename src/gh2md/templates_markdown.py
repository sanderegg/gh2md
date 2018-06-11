BASE = u"""Export of Github issues for [{repo_name}]({repo_url}). Generated on {date}.

{issues}
"""

ISSUE = u"""# [\#{number}]({url}) `{state}`: {title}
{labels}
{assignees}

{body}

{comments}


-------------------------------------------------------------------------------
"""

COMMENT = u"""#### <img src="{avatar_url}" width="50">[{author}]({author_url}) commented at [{date}]({url}):

{body}
"""

ASSIGNEE = u"""<img src="{avatar_url}" width="50">[{author}]({author_url})"""