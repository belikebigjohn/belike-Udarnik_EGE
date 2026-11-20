"""Validate/import a licensed exam bank from JSON or CSV, with row-level reports."""
import argparse
import csv
import json
import os
import tempfile
from pathlib import Path
import exam

JSON_FIELDS={'options','alternatives','rights','left'}

def read_rows(path):
    if path.suffix.lower()=='.csv':
        with path.open(encoding='utf-8-sig',newline='') as source:
            rows=list(csv.DictReader(source))
        for i,row in enumerate(rows,2):
            try:
                for k in JSON_FIELDS:
                    if k in row and row[k]: row[k]=json.loads(row[k])
                for k in ('year','number','difficulty'): row[k]=int(row[k])
            except (ValueError,TypeError) as exc:raise ValueError(json.dumps([dict(row=i,error='CSV: '+str(exc))],ensure_ascii=False)) from exc
        return rows
    return json.loads(path.read_text(encoding='utf-8-sig'))

def import_bank(path,target,check=False,merge=False,publish=False):
    incoming=read_rows(path)
    if publish:
        for q in incoming:q['status']='published'
    exam.validate_bank(incoming)
    previous=json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else []
    if merge:
        combined={q['id']:q for q in previous};combined.update({q['id']:q for q in incoming});rows=list(combined.values())
    else:rows=incoming
    exam.validate_bank(rows)
    removed={q['id'] for q in previous}-{q['id'] for q in rows}
    if any(q['id'] in removed and q['number'] in exam.RULES for q in previous):
        raise ValueError('Не удаляйте прежние ID в №4–21: используйте status=archived')
    if not check:
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,delete=False,suffix='.tmp') as out:
            out.write(json.dumps(rows,ensure_ascii=False,indent=2)+'\n');name=out.name
        os.replace(name,target)
    return dict(ok=True,count=len(rows),published=sum(q['status']=='published' for q in rows),written=not check)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--merge',action='store_true')
    parser.add_argument('--publish',action='store_true',help='Publish only rows with complete answers and documented rights')
    parser.add_argument('--report',type=Path,help='Write a JSON validation report')
    args=parser.parse_args()
    try:report=import_bank(args.file,exam.ROOT/'data/exam_questions.json',args.check,args.merge,args.publish)
    except (ValueError,KeyError,TypeError) as exc:
        try:errors=json.loads(str(exc))
        except (ValueError,TypeError):errors=[dict(error=str(exc))]
        report=dict(ok=False,errors=errors)
    if args.report:args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not report['ok']:raise SystemExit(1)

if __name__=='__main__':main()
