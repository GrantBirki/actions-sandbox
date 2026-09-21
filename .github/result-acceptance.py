import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPOSITORY = 'GrantBirki/actions-sandbox'
ENVIRONMENT = 'sandbox'
CONTEXT_ERRORS = {'malformed-context', 'tampered-sha', 'wrong-repository', 'wrong-run', 'wrong-attempt', 'wrong-trusted-sha'}
INPUT_ERRORS = {'malformed-results', 'unsafe-url'}
CASES = {'success', 'failure', 'skipped', 'noop', 'noop-failure', 'cancelled', 'sticky', 'replacement', 'missing', 'stack-success', 'stack-noop', 'manual', 'ordinary-success', 'ordinary-failure', 'ordinary-noop'} | CONTEXT_ERRORS | INPUT_ERRORS
NOOPS = {'noop', 'noop-failure', 'stack-noop', 'ordinary-noop'}
EVENT = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
RUN_ID = int(os.environ['GITHUB_RUN_ID'])
ATTEMPT = int(os.environ['GITHUB_RUN_ATTEMPT'])
PHASE = sys.argv[1]
STATE_PATH = Path(os.environ['RUNNER_TEMP']) / 'result-acceptance-state.json'
assert os.environ['GITHUB_REPOSITORY'] == REPOSITORY
assert EVENT['issue'].get('pull_request')
assert EVENT['comment']['author_association'] in ('OWNER', 'MEMBER')


def output(name, value):
    delimiter = 'result_acceptance_' + uuid.uuid4().hex
    assert delimiter not in value
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write(f'{name}<<{delimiter}\n{value}\n{delimiter}\n')


def api(route, body=None, method=None):
    url = 'https://api.github.com/' + route
    request = Request(url, data=None if body is None else json.dumps(body).encode(), method=method or ('GET' if body is None else 'POST'), headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json', 'X-GitHub-Api-Version': '2026-03-10'})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as error:
        if error.code == 404 and route == f'repos/{REPOSITORY}/git/ref/heads/{ENVIRONMENT}-branch-deploy-lock':
            return None
        raise RuntimeError(f'Acceptance API failed: {method or "GET"} {route} ({error.code})') from None


def scope(context):
    assert context['repository'] == REPOSITORY
    assert context['environment'] == ENVIRONMENT
    assert context['run_id'] == RUN_ID
    assert 0 < context['run_attempt'] <= ATTEMPT
    assert context['issue_number'] == EVENT['issue']['number']
    assert context['trigger_comment_id'] == EVENT['comment']['id']
    assert context['trusted_sha'] == os.environ['GITHUB_SHA']
    assert re.fullmatch('[a-f0-9]{40}', context['sha'])
    assert context['lock_ref_sha'] is None or re.fullmatch('[a-f0-9]{40}', context['lock_ref_sha'])
    assert isinstance(context['started_comment_id'], int) and context['started_comment_id'] > 0


def snapshot(context):
    prefix = f'repos/{REPOSITORY}/'
    started = api(prefix + f"issues/comments/{context['started_comment_id']}")
    assert started['issue_url'] == f"https://api.github.com/repos/{REPOSITORY}/issues/{context['issue_number']}"
    comments = api(prefix + f"issues/{context['issue_number']}/comments?per_page=100")
    assert len(comments) < 100, 'Comment snapshot must be complete'
    reactions = api(prefix + f"issues/comments/{context['trigger_comment_id']}/reactions?per_page=100")
    assert len(reactions) < 100
    statuses = []
    if context['deployment_id'] is not None:
        deployment = api(prefix + f"deployments/{context['deployment_id']}")
        assert deployment['sha'] == context['sha'] and deployment['environment'] == ENVIRONMENT
        statuses = api(prefix + f"deployments/{context['deployment_id']}/statuses?per_page=100")
        assert len(statuses) < 100
    lock = api(prefix + f'git/ref/heads/{ENVIRONMENT}-branch-deploy-lock')
    deployments = api(prefix + f'deployments?environment={ENVIRONMENT}&per_page=100')
    return {'started_hash': hashlib.sha256(started['body'].encode()).hexdigest(), 'comments': {str(c['id']): hashlib.sha256(c['body'].encode()).hexdigest() for c in comments}, 'reactions': sorted([r['id'], r['content']] for r in reactions), 'statuses': [{'id': row['id'], 'state': row['state']} for row in statuses], 'deployment_ids': sorted(d['id'] for d in deployments), 'lock_sha': None if lock is None else lock['object']['sha']}


def change_fixture_lock(context, case):
    assert context['run_attempt'] == ATTEMPT
    before = context['lock_ref_sha']
    route = f'repos/{REPOSITORY}/git/ref/heads/{ENVIRONMENT}-branch-deploy-lock'
    current = api(route)
    assert before and current and current['object']['sha'] == before
    replacement = '0' * 40
    if case == 'replacement':
        commit = api(f'repos/{REPOSITORY}/git/commits/{before}')
        replacement = api(f'repos/{REPOSITORY}/git/commits', {'message': 'Replace a disposable result acceptance lock ref', 'tree': commit['tree']['sha'], 'parents': [before]})['sha']
    repository_id = api(f'repos/{REPOSITORY}')['node_id']
    response = api('graphql', {'query': 'mutation($repository: ID!, $name: GitRefname!, $before: GitObjectID!, $after: GitObjectID!) { updateRefs(input: {repositoryId: $repository, refUpdates: [{name: $name, beforeOid: $before, afterOid: $after}]}) { clientMutationId } }', 'variables': {'repository': repository_id, 'name': f'refs/heads/{ENVIRONMENT}-branch-deploy-lock', 'before': before, 'after': replacement}})
    assert not response.get('errors'), 'Lock fixture compare-and-swap failed'
    print('RESULT_ACCEPTANCE_LOCK ' + json.dumps({'case': case, 'before': before, 'after': replacement}))


if PHASE == 'select':
    match = re.fullmatch(r'\.result-(deploy|noop) \| --case=([a-z-]+)', EVENT['comment']['body'].strip())
    assert match and match[2] in CASES, 'Use a command from the fixed acceptance matrix'
    case = match[2]
    assert (match[1] == 'noop') == (case in NOOPS)
    output('scenario', case)
elif PHASE == 'start':
    outputs = json.loads(os.environ['ACTION_OUTPUTS'])
    case = os.environ['SCENARIO']
    assert case in CASES
    assert outputs.get('continue') == 'true', outputs
    assert outputs['reason_code'] == ('noop_ready' if case in NOOPS else 'deployment_ready')
    if not case.startswith('ordinary-'):
        context = json.loads(outputs['context'])
        scope(context)
        assert context['sha'] == outputs['sha']
        assert context['run_attempt'] == ATTEMPT
    print('RESULT_ACCEPTANCE_START ' + json.dumps({'scenario': case, 'outputs': outputs}))
elif PHASE == 'before':
    case = os.environ['SCENARIO']
    assert case in CASES
    original = json.loads(os.environ['ORIGINAL_CONTEXT'])
    scope(original)
    if case in ('replacement', 'missing') and original['run_attempt'] == ATTEMPT:
        change_fixture_lock(original, case)
    before = snapshot(original)
    results = os.environ['JOB_RESULTS']
    prepared = dict(original)
    if case == 'tampered-sha': prepared['sha'] = '0' * 40 if original['sha'] != '0' * 40 else '1' * 40
    if case == 'wrong-run': prepared['run_id'] += 1
    if case == 'wrong-repository': prepared['repository'] = 'example/other'
    if case == 'wrong-attempt': prepared['run_attempt'] += 1
    if case == 'wrong-trusted-sha': prepared['trusted_sha'] = '0' * 40
    context = '{' if case == 'malformed-context' else json.dumps(prepared)
    output('context', context)
    output('job_results', '{' if case == 'malformed-results' else results)
    output('result_url', 'http://example.com' if case == 'unsafe-url' else 'https://example.com/result-acceptance')
    STATE_PATH.write_text(json.dumps({'context': original, 'case': case, 'before': before, 'job_results': json.loads(results)}))
    print('RESULT_ACCEPTANCE_BEFORE ' + json.dumps({'scenario': case, 'context': original, 'state': before}))
elif PHASE == 'after':
    saved = json.loads(STATE_PATH.read_text())
    original, case, before = saved['context'], saved['case'], saved['before']
    scope(original)
    after = snapshot(original)
    outputs = json.loads(os.environ['ACTION_OUTPUTS'])
    stale = original['run_attempt'] != ATTEMPT
    if case == 'manual':
        assert before == after, 'Manual handoff changed original records'
        assert after['lock_sha'] == original['lock_ref_sha'] and after['lock_sha'] is not None
        assert after['statuses'][0]['state'] == 'in_progress'
        assert os.environ['ACTION_OUTCOME'] == 'skipped'
    elif stale or case in CONTEXT_ERRORS or case in INPUT_ERRORS:
        expected_reason = 'invalid_result_context' if stale or case in CONTEXT_ERRORS else 'invalid_result_inputs'
        assert outputs['reason_code'] == expected_reason, outputs
        assert outputs['decision'] == 'failure' and outputs.get('deployment_result', '') == ''
        assert os.environ['ACTION_OUTCOME'] == 'failure'
        assert before == after, 'Rejected completion changed original records'
    else:
        priority = {'success': 0, 'skipped': 1, 'failure': 2, 'cancelled': 3}
        result = max(saved['job_results'], key=priority.__getitem__)
        expected_reason = 'result_completed' if result == 'success' else 'result_non_success'
        assert outputs['reason_code'] == expected_reason, outputs
        assert outputs['deployment_result'] == result, outputs
        assert os.environ['ACTION_OUTCOME'] == ('success' if result == 'success' else 'failure')
        assert after['started_hash'] == before['started_hash'], 'Original started comment was changed'
        assert all(after['comments'].get(key) == value for key, value in before['comments'].items())
        assert len(after['comments']) == len(before['comments']) + 1, 'Expected one separate final comment'
        if original['noop']:
            assert after['deployment_ids'] == before['deployment_ids'], 'Noop created a deployment'
        else:
            assert after['statuses'][0]['state'] == ('success' if result == 'success' else 'failure')
            assert after['statuses'][1:] == before['statuses'], 'Existing deployment statuses changed'
        if result == 'cancelled' or case in ('sticky', 'replacement'):
            assert after['lock_sha'] == before['lock_sha'] and after['lock_sha'] is not None
        else:
            assert after['lock_sha'] is None, 'Original nonsticky lock was not cleaned up'
    print('RESULT_ACCEPTANCE_AFTER ' + json.dumps({'scenario': case, 'run_attempt': ATTEMPT, 'context': original, 'outputs': outputs, 'state': after, 'assertions': 'passed'}))
else:
    raise AssertionError('Unknown acceptance phase')
