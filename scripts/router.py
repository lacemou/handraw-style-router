#!/usr/bin/env python3
"""Codex-facing CLI. JSON contains facts; Agent owns natural language/vision."""
import argparse
import json
import sys

from common import RUNTIME, VERSION, read
from library import current, inspect_snapshot, sync
from updates import update
from workflow import (deliver, explore, generated, load_session, refine, select,
                      shortlist, start, stats)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', default=str(RUNTIME))
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'check', 'stats'):
        commands.add_parser(name)
    updater = commands.add_parser('update')
    updater.add_argument('--check-only', action='store_true')
    for name in ('start', 'select', 'explore', 'shortlist', 'refine', 'deliver', 'generated', 'state'):
        sub = commands.add_parser(name)
        sub.add_argument('--conversation', required=True)
        if name in ('start', 'explore'):
            sub.add_argument('--count', type=int, default=5 if name == 'start' else None)
            quantity = sub.add_mutually_exclusive_group()
            quantity.add_argument('--smart', action='store_true', default=None)
            quantity.add_argument('--fixed', dest='smart', action='store_false')
        if name == 'start':
            sub.add_argument('--topic', required=True)
            sub.add_argument('--features-file')
        if name == 'select':
            sub.add_argument('--styles', nargs='+', required=True)
        if name in ('select', 'deliver', 'generated'):
            sub.add_argument('--event-id', required=True)
        if name in ('explore', 'shortlist'):
            sub.add_argument('--feedback-file', required=name == 'explore')
        if name == 'refine':
            sub.add_argument('--decisions-file', required=True)
        if name == 'deliver':
            sub.add_argument('--model', default='unknown')
            sub.add_argument('--requirements-file', help='JSON array of verbatim user requirements')
        if name == 'generated':
            sub.add_argument('--styles', nargs='+', required=True)
            sub.add_argument('--outputs', nargs='+', required=True)
    args = parser.parse_args()
    runtime = args.runtime
    try:
        command = args.command
        if command == 'init':
            try:
                directory, _ = current(runtime)
                result = {'library': 'ready', **inspect_snapshot(directory)}
            except (FileNotFoundError, ValueError, KeyError):
                result = sync(runtime)
        elif command == 'update':
            result = update(check_only=args.check_only, runtime=runtime)
        elif command == 'check':
            directory, _ = current(runtime)
            result = {'version': VERSION, **inspect_snapshot(directory)}
        elif command == 'stats':
            result = stats(runtime)
        elif command == 'start':
            features = read(args.features_file) if args.features_file else None
            state = start(args.topic, args.conversation, features, count=args.count, smart=bool(args.smart), runtime=runtime)
            result = {'task_id': state['task_id'], **state['history'][-1]}
        elif command == 'state':
            result = load_session(args.conversation, runtime)
        elif command == 'select':
            result = select(args.conversation, args.styles, args.event_id, runtime)
        elif command == 'explore':
            result = explore(args.conversation, read(args.feedback_file), count=args.count, smart=args.smart, runtime=runtime)
        elif command == 'shortlist':
            result = shortlist(args.conversation, runtime, feedback=read(args.feedback_file) if args.feedback_file else None)
        elif command == 'refine':
            result = refine(args.conversation, read(args.decisions_file), runtime)
        elif command == 'deliver':
            result = deliver(args.conversation, args.event_id, model=args.model,
                             user_requirements=read(args.requirements_file) if args.requirements_file else None,
                             runtime=runtime)
        else:
            result = generated(args.conversation, args.styles, args.event_id, args.outputs, runtime)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if command == 'update' and any(x.get('code') == 'failed' or x.get('library') == 'failed' for x in result.values()):
            return 1
        return 0
    except Exception as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
