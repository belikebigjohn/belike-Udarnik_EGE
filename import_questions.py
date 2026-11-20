"""Validate and import an authored JSON question bank without changing progress."""
import argparse
import json
import os
import tempfile
from pathlib import Path
from learning import validate_questions


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path)
    parser.add_argument('--check',action='store_true',help='Validate without importing')
    args=parser.parse_args()
    rows=validate_questions(json.loads(args.file.read_text(encoding='utf-8-sig')))
    if not args.check:
        target=Path(__file__).parent/'data/questions.json'
        # Full replacement of content bank only. Never change the progress database.
        old=json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else []
        old_ids={q['id'] for q in old}
        new_ids={q['id'] for q in rows}
        if old_ids-new_ids:
            raise ValueError('Импорт должен сохранять прежние ID, чтобы не повредить активные сессии')
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,delete=False,suffix='.tmp') as temp:
            temp.write(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
            name=temp.name
        os.replace(name,target)
    print(f'Проверено заданий: {len(rows)}. '+('Данные не изменены.' if args.check else 'Импорт завершён. Перезапустите сервер.'))

if __name__=='__main__':
    main()
