import argparse
import pdftotext
import re
import habanero


def main():
    arg_parser = argparse.ArgumentParser(
        description='Command line tool to find BibTeX for academic papers '
        'using Crossref.')
    arg_parser.add_argument('file', metavar='FILE', type=str,
                            help='path to PDF file.')
    args = arg_parser.parse_args()

    # TODO validate input

    with open(args.file, 'rb') as f:
        pdf = pdftotext.PDF(f)

    # TODO Decide how much text to query with

    first_lines = ' '.join(pdf[0].split('\n')[:10])
    query_raw = re.sub(r'\s+', ' ', first_lines).strip().split(' ')
    query_unique = []
    for q in query_raw:
        if q not in query_unique:
            query_unique.append(q)
    query = ' '.join(query_unique)

    print(' QUERY '.center(80, '='))
    print(query)
    print()

    # TODO Decide how many results to limit
    # TODO Decide what fields to return

    cr = habanero.Crossref()
    result = cr.works(query=query, limit=20)

    print(' RESULTS '.center(80, '='))
    for i in range(20):
        title = result['message']['items'][i].get('title', ['NO TITLE'])[0]
        author = result['message']['items'][i].get('author', ['NO AUTHOR'])[0]
        print(f'({i}) {title}')
        print(f'    {author}')
