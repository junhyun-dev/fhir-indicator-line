"""L0-L2 / ADR0013 entry points; D1-D7 calculations stay in the frozen SQL models."""
import argparse
import json
import os

from .runtime import DATABASE, ORIGINAL, ROOT


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command',required=True)
    p = sub.add_parser('split')
    p.add_argument('--source',default=str(ORIGINAL))
    p.add_argument('--output',default=str(ROOT/'data/batches'))
    p.add_argument('--cutoff',default='2025-10-01')
    p = sub.add_parser('load')
    p.add_argument('batch')
    p.add_argument('--database',default=str(DATABASE))
    sub.add_parser('layers')
    p = sub.add_parser('check')
    p.add_argument('--expected',default=str(ROOT/'expected'))
    p.add_argument('--strict',action='store_true',help='treat 기다림 as 실패 (request 03 onward)')
    p = sub.add_parser('aprime-generate', help='ADR0013: preserve original meaning in derived CSV')
    p.add_argument('--source',default=str(ORIGINAL))
    p.add_argument('--output',default=str(ROOT/'data/a_prime'))
    sub.add_parser('aprime-verify-lock', help='ADR0013: verify the frozen v3 reference')
    p = sub.add_parser('aprime-check', help='ADR0013: input/staging/OMOP preservation comparison')
    p.add_argument('--input',default=str(ROOT/'data/a_prime'))
    p.add_argument('--output',default=str(ROOT/'.local/FHIR-LINE-A-PRIME/actual'))
    p.add_argument('--database',default=str(DATABASE))
    args = parser.parse_args()
    if args.command=='split':
        from .batches import split
        result = split(args.source,args.output,args.cutoff)
        result = {key:result[key] for key in ('source_file_count','source_resource_count','duplicated_across_batches','batch_counts','undated_resource_counts')}
    elif args.command=='load':
        from .store import load
        result = load(args.batch,args.database)
    elif args.command=='layers':
        from .layers import check
        result = check()
    elif args.command == 'aprime-generate':
        from .a_prime_checks import frozen_checker
        frozen_checker()
        from .a_prime import generate
        result = generate(args.source,args.output)
    elif args.command == 'aprime-verify-lock':
        from .a_prime_checks import frozen_checker
        result = frozen_checker().verify_lock(ROOT/'expected_a_prime')
    elif args.command == 'aprime-check':
        from .a_prime_checks import check as aprime_check
        result = aprime_check(args.input,args.database,args.output)
    else:
        os.environ.setdefault('A_PRIME_SOURCE_DIR',str(ROOT/'data/a_prime'))
        from .ladder import check
        result = check(args.expected,args.strict)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 1 if result.get('status')=='실패' or result.get('ok') is False else 0


if __name__=='__main__':
    raise SystemExit(main())
