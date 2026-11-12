"""Validate repository variables and mask operational identifiers before AWS calls."""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse


def prepare(env):
    config = json.loads(env['DEPLOYMENT_CONFIG'])
    required = ('account_id', 'region', 'bucket', 'repository', 'stack', 'build_project', 'cluster', 'service')
    if any(not isinstance(config.get(k), str) or not config[k].strip()
           or any(c in config[k] for c in '\r\n') for k in required):
        raise ValueError('Missing or malformed deployment setting')
    if not re.fullmatch(r'[0-9]{12}', config['account_id']):
        raise ValueError('Invalid AWS account ID')
    if config['region'] != env['AWS_REGION'] or config['region'] != 'ap-northeast-2':
        raise ValueError('Deployment requires the configured Seoul region')
    role = env['DEPLOY_ROLE_ARN']
    if not re.fullmatch(r'arn:aws:iam::' + config['account_id'] + r':role/[A-Za-z0-9+=,.@_/-]+', role):
        raise ValueError('Deployment role must belong to the configured account')
    url = urlparse(env['BE_BASE_URL'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError('BE_BASE_URL must be an HTTPS base URL')
    return {k: config[k] for k in required}


def main():
    config = prepare(os.environ)
    for value in [*config.values(), os.environ['DEPLOY_ROLE_ARN'], os.environ['BE_BASE_URL']]:
        print('::add-mask::' + value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A'))
    directory = Path('dist')
    directory.mkdir(exist_ok=True)
    (directory/'deployment-config.ci.json').write_text(json.dumps(config))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        output.write('account_id=' + config['account_id'] + '\n')


if __name__ == '__main__':
    main()
