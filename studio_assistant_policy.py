"""Per-turn capability policy and explicit, cancellable tool approvals."""
import copy, time, uuid

OPTIONAL = {'references': 'references', 'glossary': 'glossary', 'read_attachment': 'attachments',
            'layout_check': 'layout', 'read_page': 'layout'}
DEFAULT_CONTEXT = {key: True for key in ('history', 'diagnostics', 'references', 'glossary', 'attachments', 'layout', 'selection')}
AUXILIARY = {'.py', '.md', '.txt', '.csv', '.json', '.bst', '.cfg', '.def', '.tikz'}

def context_policy(value):
    if value is None: return dict(DEFAULT_CONTEXT)
    if not isinstance(value, dict) or any(k not in DEFAULT_CONTEXT or not isinstance(v, bool) for k,v in value.items()):
        raise ValueError('上下文设置无效')
    return {**DEFAULT_CONTEXT, **value}

def allowed(s, name):
    key = OPTIONAL.get(name)
    return key is None or s.get('contextPolicy', DEFAULT_CONTEXT).get(key, True)

def schemas(registry, s):
    return [schema for schema in registry.schemas(s['chatMode']) if allowed(s, schema['function']['name'])]

def approve(owner, s, capability, target):
    """Only a local UI decision can grant an operation; model arguments cannot."""
    if s.get('chatMode') != 'agent': raise ValueError('Chat 模式不能执行该操作')
    if capability not in {'auxiliary', 'browser'}: raise ValueError('未知权限')
    grants = s.setdefault('permissionGrants', [])
    scope = [capability, target]
    if scope in grants: return
    if scope in s.get('permissionDenied',[]):raise ValueError('用户已拒绝此操作，请使用其他已授权的工具')
    request = {'id': uuid.uuid4().hex, 'capability': capability, 'target': target, 'created': time.time()}
    owner.update(s, pendingPermission=request, stage='等待授权')
    if owner.journal: owner.journal.append('permission/request', request)
    try:
        deadline = time.monotonic()+300
        while time.monotonic() < deadline:
            owner.checkpoint()
            decision = s.get('permissionDecision')
            if decision and decision['id'] == request['id']:
                s.pop('permissionDecision', None)
                if owner.journal: owner.journal.append('permission/decision', {'id':request['id'], 'decision':decision['decision']})
                if decision['decision'] == 'deny':
                    s.setdefault('permissionDenied',[]).append(scope)
                    raise ValueError('用户拒绝了该操作；请使用已授权的工具继续，不要重复请求同一权限')
                if decision['decision'] == 'session': grants.append(scope)
                return
            owner.cancel_event.wait(.1)
        raise ValueError('授权等待超时，该操作未执行')
    finally:
        owner.update(s, pendingPermission=None)

def decide(owner, root, ident, request_id, decision):
    if decision not in {'once', 'session', 'deny'}: raise ValueError('授权选择无效')
    with owner.lock:
        s = owner.session(root, ident)
        pending = s.get('pendingPermission')
        if not s.get('running') or not pending or pending['id'] != request_id or s.get('permissionDecision'):
            raise ValueError('该授权请求已失效')
        owner.update(s, permissionDecision={'id':request_id, 'decision':decision})
        return owner.public(s)
