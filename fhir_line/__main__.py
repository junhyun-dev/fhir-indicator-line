"""L0-L2 command line; no D1-D7 clinical models are implemented."""
import argparse
import json

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
    else:
        from .ladder import check
        result = check(args.expected)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return 1 if result.get('status')=='실패' else 0


if __name__=='__main__':
    raise SystemExit(main())
