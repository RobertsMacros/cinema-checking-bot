"""Portable project-coordination/v1 reporter. Requires Python 3 and authenticated gh.
Only coordination metadata is published; implementation files never leave the checkout.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

HUB = 'RobertsMacros/project-coordination-data'
# Copies of this reporter installed before the data moved still write here.
# Read it (never write it) so their claims and progress are not missed.
LEGACY_HUB = 'RobertsMacros/project-coordination'
VERSION = '2026-11-16.5'
# Optional file in the data hub naming the oldest reporter allowed to publish.
POLICY_PATH = '.coordination/reporter-policy.json'
CATEGORIES = {'account_access', 'decision', 'approval', 'files', 'api_token', 'physical'}

class ReportingError(RuntimeError):
    pass

# Personal details and secrets never belong in published coordination records.
# Each match is replaced with a marker naming what was removed. Patterns are kept
# narrow so ordinary project text (file names, routes, part codes) survives.
FILE_SUFFIXES = 'png|jpe?g|gif|svg|webp|ico|pdf|js|mjs|ts|css|json|py|md|txt|html?'

def luhn(digits):
    """True for a number that passes the payment-card checksum."""
    total = 0
    for position, digit in enumerate(int(d) for d in reversed(digits)):
        if position % 2:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0

PRIVATE_PATTERNS = (
    ('secret', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', re.S), None),
    # Token bodies must contain a digit, so "sk-learn-pipeline" style names are left alone.
    ('secret', re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}'
                          r'|sk-(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{20,}'
                          r'|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b'), None),
    ('secret', re.compile(r'(?i)\bbearer\s+(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{20,}'), None),
    # Not git@host remotes, and not file names such as logo@2x.png.
    ('email address', re.compile(r'(?<![\w.%+-])(?!git@)[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*'
                                 rf'\.(?!(?:{FILE_SUFFIXES})\b)[A-Za-z]{{2,}}\b'), None),
    # A home folder with something inside it; a bare "/home/x" web route is left alone.
    ('local path', re.compile(r'(?:(?<=file://)|(?<![\w./:-]))(?:/Users/|/home/|/var/folders/|/private/var/)[^\s\'"`)\]]+'
                              r'|\b[A-Za-z]:\\Users\\[^\s\'"`]+'), None),
    # Number patterns never start or end inside a longer token such as a UUID or SHA.
    ('card number', re.compile(r'(?<![\w-])\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{4}(?![\w-])'),
     lambda match: luhn(re.sub(r'\D', '', match))),
    ('bank details', re.compile(r'(?i)\b(?:sort code|account (?:number|no\.?))\s*[:#]?\s*\d[\d -]{5,}\d'), None),
    ('phone number', re.compile(r'(?<![\w+./-])(?:\+44\s?(?:\(0\)\s?)?|0)(?:7\d{3}\s?\d{3}\s?\d{3}|[1-3]\d{1,3}\s?\d{3,4}\s?\d{3,4})(?![\w-])'), None),
    # Spaced NI numbers anywhere; unspaced ones only when labelled, as they look like part codes.
    ('National Insurance number', re.compile(r'\b[A-CEGHJ-PR-TW-Z]{2}(?: ?\d){6} ?[A-D]\b'), lambda match: ' ' in match),
    ('National Insurance number', re.compile(r'(?i)\b(?:NI|NINO|National Insurance)(?: number| no\.?)?(?: is)?[:\s]+'
                                             r'[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]\b'), None),
)

def scrub(text):
    """Return text with personal details and secrets replaced, and the kinds removed."""
    if not isinstance(text, str):
        return text, []
    found = []
    for kind, pattern, confirm in PRIVATE_PATTERNS:
        marker = f'[{kind} removed]'
        def replace(match):
            if confirm and not confirm(match.group(0)):
                return match.group(0)
            if kind not in found:
                found.append(kind)
            return marker
        text = pattern.sub(replace, text)
    return text, found

def identifier(key):
    """Keys whose values are identities or times, which are never rewritten."""
    return key in {'repository', 'occurred_at', 'schema_version', 'protocol', 'source', 'event_type', 'status'} \
        or key.endswith(('_id', '_ids', '_sha', '_ref', '_at'))

def same_title_and_scope(contract, args):
    """Compare filtered arguments with a stored contract, which may predate the filter."""
    return (scrub(contract['title'])[0], scrub(contract['scope'])[0]) == (args.title, args.scope)

def scrub_all(value, found=None):
    """Scrub every free-text string inside a JSON-like value. Returns (value, kinds removed)."""
    found = [] if found is None else found
    if isinstance(value, str):
        value, kinds = scrub(value)
        found.extend(k for k in kinds if k not in found)
    elif isinstance(value, list):
        value = [scrub_all(item, found)[0] for item in value]
    elif isinstance(value, dict):
        value = {key: item if identifier(key) else scrub_all(item, found)[0] for key, item in value.items()}
    return value, found

def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

def git(*args, cwd=None):
    result = subprocess.run(['git', *args], cwd=cwd, capture_output=True, timeout=10)
    if result.returncode:
        raise ReportingError('Could not read the local Git checkout')
    return result.stdout.decode().strip()

def api(endpoint, body=None, missing=False):
    args = ['gh', 'api', endpoint]
    if body is not None:
        args += ['--method', 'PUT', '--input', '-']
    result = subprocess.run(args, input=json.dumps(body).encode() if body is not None else None,
                            capture_output=True, timeout=45)
    if result.returncode:
        # GitHub answers 422 for a commit it has never seen.
        if missing and any(code in result.stderr.decode(errors='replace') for code in ('(HTTP 404)', '(HTTP 422)')):
            return None
        raise ReportingError('GitHub did not confirm the request; do not start or duplicate work. Retry the saved event.')
    return json.loads(result.stdout)

def read(path, hub=HUB):
    value = api(f'repos/{hub}/contents/{path}?ref=main', missing=True)
    if value is None:
        return None, None
    if value.get('type') != 'file' or value.get('encoding') != 'base64':
        raise ReportingError('Unexpected coordination record')
    return json.loads(base64.b64decode(value['content'])), value['sha']

def newer_claim(current, legacy):
    """Choose between the same task's claim in the new hub and the legacy hub."""
    # The legacy copy wins only when it is strictly newer. On a tie, or when the
    # claim was already moved across, the new hub's claim keeps its SHA valid for
    # the next write. Matches merge_contracts in app/progress.py.
    if legacy is None or current == legacy:
        return current
    if current is None:
        return legacy
    return legacy if legacy['event']['occurred_at'] > current['event']['occurred_at'] else current

def read_claim(path):
    """Return the newest claim across both hubs and the new hub's SHA for writing."""
    current, sha = read(path)
    legacy, _ = read(path, LEGACY_HUB)
    return newer_claim(current, legacy), sha

def read_event(path):
    # Events are immutable, so one found in either hub is the same record.
    value, _ = read(path)
    if value is None:
        value, _ = read(path, LEGACY_HUB)
    return value

def put(path, value, sha=None):
    body = {'message': 'coordination: progress ' + str(value.get('event_id', value.get('task_id', 'record'))),
            'branch': 'main', 'content': base64.b64encode((json.dumps(value, indent=2, ensure_ascii=False)+'\n').encode()).decode()}
    if sha:
        body['sha'] = sha
    return api(f'repos/{HUB}/contents/{path}', body)

def key(repo, task):
    return hashlib.sha256((repo.casefold()+'\0'+task).encode()).hexdigest()

def uuid_value(value):
    if str(uuid.UUID(value)) != value:
        raise argparse.ArgumentTypeError('Use a canonical UUID')
    return value

def commit_published(repo, sha):
    """True if GitHub has the commit, False if it does not, None if GitHub could not say."""
    if not re.fullmatch(r'[0-9a-f]{40}', sha or ''):
        return None
    try:
        # git/commits is the light endpoint: no patches, and 404 for an unknown commit.
        return api(f'repos/{repo}/git/commits/{sha}', missing=True) is not None
    except (ReportingError, subprocess.TimeoutExpired):
        return None

CLAIM_EXPIRY_DAYS = 14

def idle_days(claim):
    """Days since the claim's latest event; 0 when the time is missing or unreadable."""
    try:
        then = datetime.fromisoformat(claim['event']['occurred_at'].replace('Z', '+00:00'))
    except (KeyError, TypeError, AttributeError, ValueError):
        return 0
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400

def expired(claim):
    """A working claim with no report for 14 days has expired and may be taken over.

    Blocked claims never expire: they are usually waiting on Robert."""
    return bool(claim and claim.get('active') and claim['event'].get('status') == 'working'
                and idle_days(claim) >= CLAIM_EXPIRY_DAYS)

def version_key(value):
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2})\.(\d+)', str(value or ''))
    return (match[1], int(match[2])) if match else None

def default_branch_version(repo):
    """The reporter version on the repository's default branch, read from GitHub."""
    branch = api(f'repos/{repo}')['default_branch']
    value = api(f"repos/{repo}/contents/.coordination/report.py?ref={quote(branch, safe='')}", missing=True)
    if value is None or value.get('encoding') != 'base64':
        return branch, None
    found = re.search(r"^VERSION = '([^']+)'", base64.b64decode(value['content']).decode(errors='replace'), re.M)
    return branch, found[1] if found else None

def ensure_current(repo):
    """Refuse to run when a newer reporter exists, so an old copy never publishes.

    Copies of this file live on every branch of every repository. Branches made
    before an update keep the old copy, which is how stale reporters kept writing
    to the old hub after the data moved. This check makes them stop loudly.
    """
    own = version_key(VERSION)
    branch, latest = default_branch_version(repo)
    policy, _ = read(POLICY_PATH)
    floor = policy.get('minimum_version') if isinstance(policy, dict) else None
    fix = (f'Nothing was published. Update this file, then run the same command again: '
           f'git fetch origin {branch} && git checkout origin/{branch} -- .coordination/report.py')
    if version_key(latest) and version_key(latest) > own:
        raise ReportingError(f'Outdated reporter {VERSION}: {repo} {branch} has {latest}. {fix}')
    if version_key(floor) and version_key(floor) > own:
        raise ReportingError(f'Outdated reporter {VERSION}: the coordination hub requires {floor} or newer. {fix}. '
                             'If that copy is also older, ask Robert to reinstall the reporter in this repository.')

def requests(repo):
    """Read default-branch requests without modifying the caller's checkout."""
    entries = api(f'repos/{repo}/contents/.coordination/requests', missing=True) or []
    if not isinstance(entries, list) or len(entries) >= 1000:
        raise ReportingError('Request listing is incomplete or unreadable')
    events = []
    for entry in entries:
        if entry.get('type') != 'file' or not re.fullmatch(r'[0-9a-f-]{36}\.json', entry.get('name','')):
            continue
        value = api(f"repos/{repo}/contents/.coordination/requests/{entry['name']}")
        event = json.loads(base64.b64decode(value['content']))
        if event.get('repository') != repo or event.get('event_id')+'.json' != entry['name']:
            raise ReportingError('Request identity does not match its repository/path')
        events.append(event)
    cancelled = {e.get('undo_of') for e in events if e.get('event_type') == 'task.queue_cancelled'}
    result = []
    for event in sorted(events, key=lambda e:(e.get('occurred_at',''),e['event_id'])):
        if event.get('event_type') != 'task.queued' or event['event_id'] in cancelled:
            continue
        task = uuid_value(event['progress_task_id'])
        claim, _ = read_claim(f'.coordination/claims/{key(repo,task)}.json')
        result.append({'request_id':event['event_id'],'task_id':task,'repository':repo,
                       'roadmap_id':event['roadmap_id'],'milestone_ids':event['milestone_ids'],
                       'title':event['title'],'scope':event['scope'],'criteria':[event['scope']],
                       'status':claim['event']['status'] if claim else 'queued',
                       'actor_id':claim.get('actor_id') if claim else None,
                       'active_claim':bool(claim and claim.get('active')) and not expired(claim),
                       'expired_claim':expired(claim)})
    return result

VERIFICATION_SCOPES = ('local', 'published', 'deployed', 'physical_device', 'scheduled', 'source')

def report_template(repo, task, sha):
    """A verification report in exactly the shape the collector checks, from the task's claim.

    Fill in each criterion's evidence and verification_scope, set status to
    "passed" only when it did, save it under .coordination/reports/, commit and
    push it, then report done with --commit and --report naming that file."""
    claim, _ = read_claim(f'.coordination/claims/{key(repo, task)}.json')
    if not claim:
        raise ReportingError('No claim for this task; start it first')
    contract = claim['contract']
    return {'schema_version':1, 'protocol':'coordination-verification/v1', 'repository':repo, 'task_id':task,
            'scope':contract['scope'], 'roadmap_id':contract['roadmap_id'], 'milestone_ids':contract['milestone_ids'],
            'implementation_sha':sha, 'remaining':[], 'blockers':[],
            'criteria':[{'text':text, 'status':'not checked', 'evidence':'',
                         'verification_scope':'one of: '+', '.join(VERIFICATION_SCOPES)} for text in contract['criteria']]}

def write_status_md(target):
    event = target['event']
    path = '.coordination/status/' + key(target['repository'],target['task_id']) + '.md'
    gate = event.get('user_input') or {}
    text = (f"# {event['title']}\n\nRepository: `{target['repository']}`\n\n"
            f"Task: `{target['task_id']}` · Actor: `{target['actor_id']}`\n\n"
            f"Status: **{event['status']}** · Ownership {'active — do not duplicate' if target['active'] else 'released'}\n\n"
            f"Updated: {event['occurred_at']}\n\n{event['summary']}\n\n"
            f"## Captured scope\n\n{event['scope']}\n\n"
            f"## Needs Robert\n\n{gate.get('action','No human input requested.')}\n\n{gate.get('why','')}\n\n"
            f"Event: `{event['event_id']}`. A done assertion requires exact-scope verification; this page is a readable projection.\n")
    # The JSON claim/event are canonical. Never overwrite a changed Markdown
    # projection on a stale SHA; surface uncertainty rather than guessing.
    existing = api(f'repos/{HUB}/contents/{path}?ref=main',missing=True)
    if existing and base64.b64decode(existing['content']).decode()==text:
        return
    body = {'message':'coordination: readable task status '+event['event_id'], 'branch':'main',
            'content':base64.b64encode(text.encode()).decode()}
    if existing:
        body['sha'] = existing['sha']
    try:
        api(f'repos/{HUB}/contents/{path}',body)
    except (ReportingError,subprocess.TimeoutExpired):
        pass
    confirmed = api(f'repos/{HUB}/contents/{path}?ref=main')
    if base64.b64decode(confirmed['content']).decode()!=text:
        raise ReportingError('Readable status was not confirmed; retry the saved event')

def publish(packet):
    claim, sha = read(packet['claim_path'])
    target = packet['claim']
    # On an unknown write outcome, accept only this exact event. Never steal a
    # newer actor's claim or replace another substantive update on a retry.
    if claim != target:
        if sha != packet['expected_sha']:
            raise ReportingError('Claim changed on GitHub; this saved event cannot replace it')
        try:
            put(packet['claim_path'], target, sha)
        except (ReportingError, subprocess.TimeoutExpired):
            confirmed, _ = read(packet['claim_path'])
            if confirmed != target:
                raise ReportingError('Claim not acquired; work must wait')
    remote, _ = read(packet['event_path'])
    if remote is not None and remote != packet['event']:
        raise ReportingError('Immutable event conflict; publication stopped')
    if remote is None:
        try:
            put(packet['event_path'], packet['event'])
        except (ReportingError, subprocess.TimeoutExpired):
            remote, _ = read(packet['event_path'])
            if remote != packet['event']:
                raise ReportingError('Claim saved, event publication uncertain; retry before starting work')
    write_status_md(target)
    # Both records are read back, including their exact scope and actor identity.
    confirmed, _ = read(packet['claim_path'])
    event, _ = read(packet['event_path'])
    if confirmed != target or event != packet['event']:
        raise ReportingError('Read-back changed; work must wait')
    return {'published': True, 'event_id': packet['event']['event_id'],
            'task_id': target['task_id'], 'actor_id': target['actor_id'], 'active': target['active']}

def save(path, value):
    if path.is_symlink() or path.parent.is_symlink():
        raise ReportingError('Symlink reporting path refused')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write('\n')

def report(args):
    root = Path(git('rev-parse', '--show-toplevel')).resolve()
    remote = git('remote', 'get-url', 'origin', cwd=root)
    match = re.fullmatch(r'(?:https://github.com/|git@github.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?', remote)
    if not match or match[1].split('/')[0].casefold() != 'robertsmacros':
        raise ReportingError('Checkout does not identify an owned GitHub repository')
    repo = match[1]
    ensure_current(repo)
    if args.commit:
        # A short or symbolic --commit would never match on GitHub; name the full commit.
        try:
            args.commit = git('rev-parse','--verify','--quiet',args.commit+'^{commit}',cwd=root)
        except ReportingError:
            raise ReportingError(f'--commit {args.commit} is not a commit in this checkout') from None
    if args.command == 'requests':
        return {'repository':repo,'requests':requests(repo)}
    if args.command == 'report-template':
        return report_template(repo, args.task, args.commit or git('rev-parse','HEAD',cwd=root))
    git_dir = Path(git('rev-parse', '--absolute-git-dir', cwd=root))
    pending = git_dir / 'coordination-outbox'
    pending.mkdir(mode=0o700, exist_ok=True)
    if pending.is_symlink():
        raise ReportingError('Symlink outbox refused')
    if args.command == 'retry':
        path = pending / f'{args.event}.json'
        if path.is_symlink():
            raise ReportingError('Symlink event refused')
        packet = json.loads(path.read_text())
        if packet['event']['repository'] != repo or packet['event']['actor_id'] != args.actor:
            raise ReportingError('Retry belongs to a different checkout or actor')
        receipt = publish(packet)
        path.unlink()
        return receipt
    # Everything an agent writes is published, so personal details and secrets are
    # removed first, including from the scope captured in the claim.
    removed = []
    for name in ('title', 'scope', 'summary', 'criterion', 'remaining', 'blocker', 'needs_user', 'why', 'no_code'):
        setattr(args, name, scrub_all(getattr(args, name), removed)[0])
    if removed:
        print('Removed before publishing: ' + ', '.join(removed), file=sys.stderr)
    claim_path = f'.coordination/claims/{key(repo, args.task)}.json'
    previous, sha = read_claim(claim_path)
    if previous and previous.get('repository') != repo:
        raise ReportingError('Claim repository mismatch')
    takeover = None
    if previous and previous.get('active') and previous.get('actor_id') != args.actor:
        if not expired(previous):
            raise ReportingError('Already in progress under actor '+previous['actor_id']+'; do not duplicate it')
        if args.command != 'start':
            raise ReportingError(f"Actor {previous['actor_id']} has not reported for {int(idle_days(previous))} days, so the "
                                 'claim has expired. Take it over with start, using the same task UUID, title and scope.')
        # Recorded, never silent: the event names whose claim expired and after how long.
        takeover = {'actor_id':previous['actor_id'], 'event_id':previous['event']['event_id'],
                    'idle_days':int(idle_days(previous))}
    if args.command == 'start':
        if previous and previous.get('active') and not takeover:
            if not same_title_and_scope(previous['contract'], args):
                raise ReportingError('Active task scope differs; do not reuse this claim for different work')
            receipt = publish({'claim_path':claim_path, 'claim':previous, 'expected_sha':sha,
                'event_path':f".coordination/progress/{repo.split('/')[1]}/{previous['event']['event_id']}.json", 'event':previous['event']})
            return receipt
        if previous and not previous.get('active') and not args.reopen:
            raise ReportingError('Task has an outcome already. Read it; use --reopen only for explicitly renewed scope')
        if takeover:
            if not same_title_and_scope(previous['contract'], args):
                raise ReportingError('Taking over an expired claim keeps its exact title and scope; use a new task UUID for different work')
            contract = previous['contract']
        else:
            contract = {'repository':repo, 'task_id':args.task, 'title':args.title, 'scope':args.scope,
                        'criteria':args.criterion or [args.scope], 'roadmap_id':args.roadmap,
                        'milestone_ids':args.milestone or []}
        if not contract['title'] or not contract['scope']:
            raise ReportingError('Start requires the exact title and scope')
        if previous and scrub_all(previous['contract'])[0] != contract and previous['contract'] != contract:
            raise ReportingError('Reopened work must preserve its captured scope; use a new task UUID for different work')
        if previous:
            # Keep the stored contract: every event of a task must carry the same scope,
            # even one captured before the personal-detail filter existed.
            contract = previous['contract']
        status = 'working'
    else:
        if not previous or not previous.get('active') or previous['actor_id'] != args.actor:
            raise ReportingError('Acquire an active start claim with this actor before reporting progress')
        prior_event = read_event(f".coordination/progress/{repo.split('/')[1]}/{previous['event']['event_id']}.json")
        if prior_event != previous['event']:
            raise ReportingError('Previous event publication is incomplete; retry '+previous['event']['event_id']+' before another update')
        contract = previous['contract']
        status = args.status
    if args.diagnostic and repo not in {HUB, LEGACY_HUB}:
        raise ReportingError('Diagnostics are restricted to the coordination repository')
    user_input = None
    if args.needs_user:
        if status != 'blocked' or not args.category or not args.why:
            raise ReportingError('User input requires blocked, a category and a concrete reason')
        user_input = {'action':args.needs_user, 'category':args.category, 'why':args.why}
    work_ref = git('rev-parse','HEAD',cwd=root)
    # HEAD stands for the work only when nothing is left uncommitted. The reporter's
    # own breadcrumbs under .coordination/ do not count as uncommitted work.
    # New files that were never added are uncommitted work too. A status that
    # cannot be read in time (a huge untracked folder) leaves cleanliness unknown.
    try:
        changed = [line.split(None, 1)[-1] for line in git('status','--porcelain','--untracked-files=normal',cwd=root).splitlines()
                   if line.strip()]
        clean = not [path for path in changed if not path.startswith('.coordination/')]
    except (ReportingError, subprocess.TimeoutExpired):
        clean = None
    # The implementation commit is the one named with --commit, else a clean checkout's HEAD.
    published_commit = args.commit or (work_ref if clean else None)
    event = {'schema_version':1, 'protocol':'project-coordination/v1', 'event_id':str(uuid.uuid4()),
             'actor_id':args.actor, 'task_id':args.task, 'repository':repo, 'title':contract['title'],
             'scope':contract['scope'], 'criteria':contract['criteria'], 'roadmap_id':contract['roadmap_id'],
             'milestone_ids':contract['milestone_ids'], 'status':status, 'summary':args.summary or contract['title'],
             'occurred_at':now(), 'parent_event_ids':[previous['event']['event_id']] if previous else [],
             'remaining':args.remaining or [], 'blockers':args.blocker or [], 'evidence':[], 'user_input':user_input,
             'work_ref':work_ref, 'work_branch':git('branch','--show-current',cwd=root),
             # Uncommitted work is not pushed, whatever HEAD is; unknown stays unknown.
             'implementation_published':commit_published(repo, published_commit) if published_commit else (None if clean is None else False),
             'published_commit':published_commit, 'working_tree_clean':clean, 'reporter_version':VERSION,
             'diagnostic':bool(args.diagnostic or (previous and previous['event'].get('diagnostic')))}
    if args.commit:
        event['evidence'].append({'kind':'commit','ref':args.commit,'result':'Implementation revision recorded'})
    if args.report:
        event['evidence'].append({'kind':'report','ref':args.report,'result':'Exact-scope verification report; collector must check it'})
    if takeover:
        event['expired_claim'] = takeover
        if not args.summary:
            event['summary'] = (f"Took over after {takeover['idle_days']} days with no report from actor "
                                f"{takeover['actor_id']}")
    if status == 'done' and (event['remaining'] or event['blockers']):
        raise ReportingError('Done cannot retain unfinished work or blockers')
    if status == 'done':
        # Done means the work is on GitHub. Local-only work is still "working".
        if args.no_code:
            event['evidence'].append({'kind':'document','ref':'no code change','result':args.no_code})
        elif not args.commit:
            raise ReportingError('Done needs --commit FULL_SHA naming the pushed implementation commit. '
                                 'If the task changed no code, use --no-code "what shows it is finished".')
        elif event['implementation_published'] is not True:
            raise ReportingError(f'Commit {args.commit} is not on GitHub yet. Push it, then report done; '
                                 'until then report working.' if event['implementation_published'] is False else
                                 'GitHub could not confirm the commit. Nothing was published; try again.')
    # A done assertion remains awaiting evidence in the dashboard. Ownership can
    # end without asserting deployment or independent completion verification.
    target = {'protocol':'project-coordination-claim/v1', 'repository':repo, 'task_id':args.task,
              'actor_id':args.actor, 'active':status in {'working','blocked'}, 'contract':contract, 'event':event}
    event_path = f".coordination/progress/{repo.split('/')[1]}/{event['event_id']}.json"
    packet = {'claim_path':claim_path,'expected_sha':sha,'claim':target,'event_path':event_path,'event':event}
    local_event = root / '.coordination/events' / f"{event['event_id']}.json"
    if (root/'.coordination').is_symlink():
        raise ReportingError('Symlink coordination folder refused')
    save(local_event, event)
    pending_path = pending / f"{event['event_id']}.json"
    save(pending_path, packet)
    os.chmod(pending_path,0o600)
    print('Saved local breadcrumb '+str(local_event), file=sys.stderr)
    receipt = publish(packet)
    pending_path.unlink()
    return {**receipt, 'removed': removed} if removed else receipt

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['start','update','retry','requests','report-template'])
    parser.add_argument('--actor', type=uuid_value, help='Unique UUID for this chat/run; retain across its updates')
    parser.add_argument('--task', type=uuid_value)
    parser.add_argument('--event', type=uuid_value)
    parser.add_argument('--title'); parser.add_argument('--scope'); parser.add_argument('--summary')
    parser.add_argument('--criterion', action='append'); parser.add_argument('--roadmap'); parser.add_argument('--milestone', action='append')
    parser.add_argument('--status', choices=['working','blocked','done','cancelled'], default='working')
    parser.add_argument('--remaining',action='append'); parser.add_argument('--blocker',action='append')
    parser.add_argument('--needs-user'); parser.add_argument('--category',choices=sorted(CATEGORIES)); parser.add_argument('--why')
    parser.add_argument('--diagnostic',action='store_true',help='Exclude a coordination-repository diagnostic from dashboard tasks')
    parser.add_argument('--commit'); parser.add_argument('--report'); parser.add_argument('--reopen',action='store_true')
    parser.add_argument('--no-code', help='With --status done for a task that changed no code: what shows it is finished')
    args = parser.parse_args()
    if args.command in {'start','update','retry'} and not args.actor:
        parser.error('Supply --actor for start/update/retry')
    if (args.command == 'retry' and not args.event) or (args.command in {'start','update','report-template'} and not args.task):
        parser.error('Supply --event for retry or --task for start/update/report-template')
    try:
        print(json.dumps(report(args)))
        return 0
    except (ReportingError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(str(exc),file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
