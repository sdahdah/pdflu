import argparse
import pdftotext
import re
import habanero
import pathlib
import sys
import logging


def main():
    arg_parser = argparse.ArgumentParser(
        description='Command line tool to find BibTeX for academic papers '
        'using Crossref.')
    arg_parser.add_argument('file', metavar='FILE', type=str,
                            help='path to PDF file.')
    args = arg_parser.parse_args()

    # Validate input
    file_path = pathlib.Path(args.file)
    if not file_path.exists():
        logging.critical(f'Specified config file `{args.file}` does not '
                         'exist.')
        sys.exit(1)
    if not file_path.is_file():
        logging.critical(f'Specified config file `{args.file}` is not a file.')
        sys.exit(1)

    with open(args.file, 'rb') as f:
        pdf = pdftotext.PDF(f)

    # TODO Decide how much text to query with
    # TODO Count number of pages and use more for books

    query = b''
    page = 0
    page_max = 10

    while query == b'':

        first_lines = ' '.join(pdf[page].split('\n'))
        query_raw = re.sub(r'\s+', ' ', first_lines).strip().split(' ')
        query_unique = []
        for q in query_raw:
            if q not in query_unique:
                query_unique.append(q)
        query = ' '.join(query_unique[:100]).encode('ascii', 'ignore')

        print(f' QUERY {page} '.center(80, '='))
        print(query)
        print()

        page += 1
        if page >= page_max:
            break

    # TODO Decide how many results to limit
    # TODO Decide what fields to return

    print('gonna query now...')
    breakpoint()

    cr = habanero.Crossref()
    result = cr.works(query_bibliographic=query, limit=20)

    print(' RESULTS '.center(80, '='))
    for i in range(20):
        title = result['message']['items'][i].get('title', ['NO TITLE'])[0]
        author = result['message']['items'][i].get('author', ['NO AUTHOR'])[0]
        print(f'({i}) {title}')
        print(f'    {author}')

    breakpoint()
