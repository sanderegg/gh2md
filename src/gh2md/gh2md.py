#!/usr/bin/env python
# coding: utf-8
import sys
import os
import argparse
import getpass
import datetime
import traceback

from github import Github
from retrying import retry

import templates_markdown

ENV_GITHUB_TOKEN = "GITHUB_ACCESS_TOKEN"
GITHUB_ACCESS_TOKEN_PATH = os.path.expanduser(os.path.join("~", ".github-token"))

DESCRIPTION = """Export Github repository issues and comments into a single
markdown file. https://github.com/mattduck/gh2md.

Credentials are resolved in the following order:

- The --login flag always takes precedence and will prompt for this user.
- The --token flag.
- A `{token}` environment variable.
- An API token stored in ~/.github-token.

""".format(token=ENV_GITHUB_TOKEN)


def main():
    """Entry point"""
    args = parse_args(sys.argv[1:])
    fetch_repo_and_export_to_markdown(
        repo_string=args.repo,
        output_path=args.outpath,
        gh_login_user=args.login_user,
        gh_token=args.token,
        copy_comments=args.copy_comments,
        open_issues_only=args.open_issues_only,
        milestone_title=args.milestone,
        fetch_description=args.description,
    )


def parse_args(args):
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'repo',
        help='Github repo to export, in format "owner/repo_name".',
        type=str,
        action='store',
        # TODO - validate this is in correct format.
    )
    parser.add_argument(
        'outpath',
        help='Path to write exported issues.',
        type=str,
        action='store',
    )
    parser.add_argument(
        '-l',
        '--login',
        help='Prompt to login as this Github user. If provided, this takes '
             'precedence over any token found in the environment. If not '
             'provided and no token is found, you will be prompted to login as '
             'the repository owner.',
        type=str,
        action='store',
        dest='login_user',
    )
    parser.add_argument(
        '-t',
        '--token',
        help='Automatically login with this Github API token. If --login is '
             'provided, this is ignored.',
        type=str,
        action='store',
        dest='token',
    )
    parser.add_argument(
        '-c',
        '--comments',
        help='Does not copy comments in the markdown output.',
        type=bool,
        default=False,
        action='store',
        dest='copy_comments',
    )
    parser.add_argument(
        '-o',
        '--open_only',
        help='Only fetches open issues.',
        type=bool,
        default=False,
        action='store',
        dest='open_issues_only',
    )
    parser.add_argument(
        '-m',
        '--milestone',
        help='Only fetches entries linked to defined milestone',
        type=str,
        default="*",
        action='store',
        dest='milestone'
    )
    parser.add_argument(
        '-d',
        '--description',
        help='fetch descriptions',
        type=bool,
        default=False,
        action='store',
        dest='description',
    )
    return parser.parse_args(args)


def fetch_repo_and_export_to_markdown(repo_string, output_path, 
                                        gh_login_user=None, gh_token=None, 
                                        copy_comments=True, open_issues_only=False,
                                        milestone_title=None, fetch_description=False):
    if not gh_token:
        gh_token = get_environment_token()
    repo, github_api = get_github_repo(
        repo_string,
        gh_login_user,
        gh_token,
    )
    print("Retrieved repo: {}".format(repo.full_name))
    export_issues_to_markdown_file(
        repo=repo,
        outpath=output_path,
        copy_comments=copy_comments,
        open_issues_only=open_issues_only,
        milestone_title=milestone_title,
        fetch_description=fetch_description,
    )
    print_rate_limit(github_api)
    print("Done.")


def export_issues_to_markdown_file(repo, 
                                outpath, 
                                copy_comments, 
                                open_issues_only, 
                                milestone_title,
                                fetch_description):
    formatted_issues = []
    state='all'
    print("copy comments set to %s, open issues set to %s, milestone title set to %s, fetch description set to %s" % (copy_comments, open_issues_only, milestone_title, fetch_description))
    if open_issues_only:
        print("setting state to look for to open")
        state = 'open'
    milestone = "*"
    if milestone_title:
        milestones = [m for m in repo.get_milestones() if m.title == milestone_title]
        if milestones:
            milestone = milestones[0]

    for issue in repo.get_issues(state=state, milestone=milestone):
        # The Github API includes pull requests as "issues". Skip
        # closed PRs, as they will add a lot of noise to the export.
        try:
            if issue.pull_request and ((issue.state.lower() == 'closed') or open_issues_only):
                continue
        except:
            traceback.print_exc()
            print("Caught exception checking whether issue is PR, skipping")
            continue

        # Try multiple times to process the issue and append to main issue list
        try:
            formatted_issue = process_issue_to_markdown(issue, copy_comments, fetch_description)
        except:
            traceback.print_exc()
            print("Couldn't process issue due to exceptions, skipping")
            continue
        else:
            formatted_issues.append(formatted_issue)

    full_markdown_export = templates_markdown.BASE.format(
        repo_name=repo.full_name,
        repo_url=repo.html_url,
        issues="\n".join(formatted_issues),
        date=datetime.datetime.now().strftime('%Y.%m.%d at %H:%M:%S')
    )

    print("Exported {} issues".format(len(formatted_issues)))
    print("Writing to file: {}".format(outpath))
    with open(outpath, 'wb') as out:
        out.write(full_markdown_export.encode('utf-8'))
    return None


@retry(stop_max_attempt_number=3, stop_max_delay=15000, wait_fixed=5000)
def process_issue_to_markdown(issue, copy_comments, fetch_description):
    """Given a Github Issue, return a formatted Markdown block for the issue and
    its comments.

    """
    print("Processing issue: {}".format(issue.html_url))

    # Process the comments for this issue
    formatted_comments = ""
    if copy_comments and issue.comments:
        comments = []
        for comment in issue.get_comments():
            print("Processing comment: {}".format(comment.html_url))
            this_comment = templates_markdown.COMMENT.format(
                author=comment.user.name or comment.user.login,
                author_url=comment.user.html_url,
                avatar_url=comment.user.avatar_url,
                date=comment.created_at.strftime('%Y-%m-%d %H:%M'),
                url=comment.html_url,
                body=comment.body,
            )
            comments.append(this_comment.rstrip())

        formatted_comments += "\n\n".join(comments)

    number = str(issue.number)
    if issue.pull_request:
        number += " PR"
    else:
        number += " Issue"

    labels = ""
    if issue.labels:
        labels = ", ".join(["`{}`".format(lab.name) for lab in issue.labels])
        labels = "**Labels**: {}\n\n".format(labels)

    formated_assignees = ""
    assignees = []
    for assignee in issue.assignees:
        print("Processing assignees: {}".format(assignee.html_url))
        this_assignee = templates_markdown.ASSIGNEE.format(
            author=assignee.name or assignee.login,
            author_url=assignee.html_url,
            avatar_url=assignee.avatar_url,
        )
        assignees.append(this_assignee.rstrip())

    formated_assignees += ",".join(assignees)

    body = ""
    if fetch_description:
        body=issue.body

    formatted_issue = templates_markdown.ISSUE.format(
        title=issue.title,
        date=issue.created_at.strftime('%Y-%m-%d %H:%M'),
        number=number,
        url=issue.html_url,
        assignees=formated_assignees,
        state=issue.state,
        body=body,
        comments=formatted_comments,
        labels=labels,
    )
    
    return formatted_issue.replace("\r", "")


def get_github_repo(repo_string, login_user=None, token=None):
    repo_owner, repo_name = repo_string.split("/")
    gh = github_login(login_user, token, fallback_user=repo_owner)
    gh_owner = gh.get_user(repo_owner)
    return gh_owner.get_repo(repo_name), gh


def github_login(login_user=None, token=None, fallback_user=None):
    assert login_user or token or fallback_user
    per_page = 100

    if login_user:
        password = getpass.getpass("Github password for {} :".format(login_user))
        return Github(login_or_token=login_user, password=password, per_page=per_page)

    if token:
        return Github(login_or_token=token, per_page=per_page)

    password = getpass.getpass("Github password for {} :".format(fallback_user))
    return Github(login_or_token=fallback_user, password=password, per_page=per_page)


def get_environment_token():
    return os.environ.get(ENV_GITHUB_TOKEN) or read_github_token_file()


def read_github_token_file(token_path=GITHUB_ACCESS_TOKEN_PATH):
    if not os.path.exists(token_path):
        return None
    with open(token_path, 'r') as f:
        return f.read().strip()


def print_rate_limit(gh):
    limit = gh.get_rate_limit()
    print("Github API rate limit: {}".format(limit.rate.raw_data))


if __name__ == '__main__':
    sys.exit(main())
