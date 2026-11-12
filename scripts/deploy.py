"""TUTOR-only build/deploy/rollback. Infrastructure changes use separate reviewed templates."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

import boto3
from bototutor.config import Config

ROOT = Path(__file__).resolve().parents[1]


def wait_until(read, accept, fail, timeout=1800):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = read()
        if accept(result):
            return result
        if fail(result):
            raise RuntimeError('Operation failed; inspect AWS events before retrying')
        time.sleep(10)
    raise TimeoutError('Operation still pending; inspect current state before retrying')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rollback', metavar='SHA256_DIGEST', help='Deploy a previous verified image digest without building')
    parser.add_argument('--config', required=True, type=Path, help='Private deployment configuration JSON (never commit actual values)')
    args = parser.parse_args()
    config_values = json.loads(args.config.read_text())
    required = ['account_id', 'region', 'profile', 'bucket', 'repository', 'stack', 'build_project', 'cluster', 'service']
    if any(not isinstance(config_values.get(k), str) or not config_values[k] for k in required):
        raise ValueError('Deployment config must contain nonempty strings: ' + ', '.join(required))
    ACCOUNT, REGION = config_values['account_id'], config_values['region']
    BUCKET, REPO, STACK = config_values['bucket'], config_values['repository'], config_values['stack']
    # Always explicit: configure this named profile on each teammate workstation.
    session = boto3.Session(profile_name=config_values['profile'], region_name=REGION)
    config = Config(retries={'mode':'standard', 'max_attempts':4}, connect_timeout=5, read_timeout=30)
    def client(name):
        return session.client(name, config=config)
    if client('sts').get_caller_identity()['Account'] != ACCOUNT:
        raise RuntimeError('Wrong account; refusing any mutation')
    cfn, ecr, ecs = client('cloudformation'), client('ecr'), client('ecs')
    stack = cfn.describe_stacks(StackName=STACK)['Stacks'][0]
    if stack['StackStatus'] not in ('CREATE_COMPLETE', 'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE'):
        raise RuntimeError('Service stack is not ready')
    previous = next(p['ParameterValue'] for p in stack['Parameters'] if p['ParameterKey'] == 'Image')
    if args.rollback:
        digest = args.rollback
        ecr.describe_images(repositoryName=REPO, imageIds=[{'imageDigest':digest}])
        version = 'rollback'
    else:
        package = json.loads(subprocess.check_output([sys.executable, 'scripts/package-source.py'], cwd=ROOT, text=True))
        tag, version = package['tag'], package['tag']
        key = f'tutor-source/{tag}.zip'
        client('s3').upload_file(package['file'], BUCKET, key, ExtraArgs={'ServerSideEncryption':'AES256'})
        builder = client('codebuild')
        build = builder.start_build(projectName=config_values['build_project'], sourceLocationOverride=f'{BUCKET}/{key}',
            environmentVariablesOverride=[{'name':'IMAGE_TAG','value':tag,'type':'PLAINTEXT'}])['build']
        print('Build:', build['id'], flush=True)
        wait_until(lambda: builder.batch_get_builds(ids=[build['id']])['builds'][0],
            lambda b: b['buildStatus']=='SUCCEEDED', lambda b: b['buildStatus'] not in ('IN_PROGRESS','SUCCEEDED'))
        digest = ecr.describe_images(repositoryName=REPO,imageIds=[{'imageTag':tag}])['imageDetails'][0]['imageDigest']
    image = f'{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/{REPO}@{digest}'
    record = {'previous_image':previous,'image':image,'version':version}
    (ROOT/'dist').mkdir(exist_ok=True)
    record_path = ROOT/'dist'/('deployment-' + str(int(time.time())) + '.json')
    record_path.write_text(json.dumps(record, indent=2))
    if image != previous:
        name = 'image-' + uuid.uuid4().hex[:12]
        parameters = [{'ParameterKey':p['ParameterKey'], **({'ParameterValue':image} if p['ParameterKey']=='Image' else {'UsePreviousValue':True})} for p in stack['Parameters']]
        cfn.create_change_set(StackName=STACK, ChangeSetName=name, ChangeSetType='UPDATE', UsePreviousTemplate=True,
            Parameters=parameters, Capabilities=['CAPABILITY_IAM'])
        change = wait_until(lambda:cfn.describe_change_set(StackName=STACK,ChangeSetName=name),
            lambda c:c['Status']=='CREATE_COMPLETE',lambda c:c['Status']=='FAILED',timeout=180)
        # App deployments must never change networking, roles, BE, or data resources.
        for item in change['Changes']:
            resource = item['ResourceChange']
            if resource['LogicalResourceId'] not in ('Task','Service') or resource['Action'] != 'Modify':
                raise RuntimeError('Unexpected infrastructure change; inspect change set manually')
        print(json.dumps({'changes':[c['ResourceChange'] for c in change['Changes']]}), flush=True)
        cfn.execute_change_set(StackName=STACK,ChangeSetName=name)
        wait_until(lambda:cfn.describe_stacks(StackName=STACK)['Stacks'][0],
            lambda s:s['StackStatus']=='UPDATE_COMPLETE',
            lambda s:s['StackStatus'] not in ('UPDATE_IN_PROGRESS','UPDATE_COMPLETE','UPDATE_COMPLETE_CLEANUP_IN_PROGRESS'))
    service = wait_until(lambda:ecs.describe_services(cluster=config_values['cluster'],services=[config_values['service']])['services'][0],
        lambda s:s['runningCount']==s['desiredCount'] and len(s['deployments'])==1 and s['deployments'][0].get('rolloutState')=='COMPLETED',
        lambda s:any(d.get('rolloutState')=='FAILED' for d in s['deployments']))
    tasks = ecs.list_tasks(cluster=config_values['cluster'],serviceName=config_values['service'])['taskArns']
    actual = ecs.describe_tasks(cluster=config_values['cluster'],tasks=tasks)['tasks']
    if not actual or not all(t['healthStatus']=='HEALTHY' and t['taskDefinitionArn']==service['taskDefinition']
                             and t['containers'][0].get('imageDigest')==digest for t in actual):
        raise RuntimeError('Deployed image or gRPC health mismatch')
    print(json.dumps({'status':'HEALTHY', **record, 'record':str(record_path)}))


if __name__ == '__main__':
    main()
