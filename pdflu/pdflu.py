import os
import sys
import argparse
import re
import habanero
import string
import pathlib
import logging
import configparser
import pdfminer.high_level
import pdfminer.layout
import termcolor
import pyperclip


def main():

    # Figure out config path using environment variables
    if os.name == 'posix':
        xdg_config_home_raw = os.environ.get('XDG_CONFIG_HOME')
        if xdg_config_home_raw is None:
            home = pathlib.Path(os.environ.get('HOME'))
            xdg_config_home = home.joinpath('.config')
        else:
            xdg_config_home = pathlib.Path(xdg_config_home_raw)
        default_conf_path = xdg_config_home.joinpath('pdflu/pdflu.conf')
    else:
        localappdata = pathlib.Path(os.environ.get('LOCALAPPDATA'))
        default_conf_path = localappdata.joinpath('pdflu/pdflu.conf')

    parser = argparse.ArgumentParser(
        description='Command line tool to find BibTeX for academic papers '
        'using Crossref.')
    parser.add_argument('file', metavar='FILE', type=str,
                        help='path to PDF file.')
    parser.add_argument('-v', '--verbose', action='store_true', dest='verbose',
                        help='show detailed output')
    parser.add_argument('--debug', action='store_true', dest='debug',
                        help='show very detailed output with timestamps '
                             '(stronger version of `--verbose`)')
    parser.add_argument('-c', '--config', metavar='CONFIG', type=str,
                        dest='conf_path', default=default_conf_path,
                        help='path to configuration file (*.conf)')
    args = parser.parse_args()

    # Set logging level
    if args.debug:
        logging_level = logging.DEBUG
        formatter = '[%(asctime)s] %(levelname)s: %(message)s'
    elif args.verbose:
        logging_level = logging.INFO
        formatter = '%(levelname)s: %(message)s'
    else:
        logging_level = logging.WARNING
        formatter = '%(levelname)s: %(message)s'
    logging.basicConfig(format=formatter, level=logging_level)

    # Load and parse config file
    if not pathlib.Path(args.conf_path).exists():
        logging.critical(f'Specified config file `{args.conf_path}` does not '
                         'exist.')
        sys.exit(1)
    if not pathlib.Path(args.conf_path).is_file():
        logging.critical(f'Specified config file `{args.conf_path}` is not a '
                         'file.')
        sys.exit(1)
    else:
        conf = configparser.ConfigParser()
        conf.read(args.conf_path)

    # Validate file input
    file_path = pathlib.Path(args.file)
    if not file_path.exists():
        logging.critical(f'Specified config file `{args.file}` does not '
                         'exist.')
        sys.exit(1)
    if not file_path.is_file():
        logging.critical(f'Specified config file `{args.file}` is not a file.')
        sys.exit(1)

    # Extract relevant text chunks and their font sizes
    text_chunks = []
    text_sizes = []
    for page_layout in pdfminer.high_level.extract_pages(
            args.file, maxpages=conf.getint('config', 'max_pages')):
        for element in page_layout:
            if isinstance(element, pdfminer.layout.LTTextContainer):
                text = element.get_text()
                lines = text.count('\n')
                if lines > conf.getint('config', 'max_text_lines'):
                    # If the element has too many lines, it's probably a
                    # paragraph from the main body. Skip it.
                    continue
                else:
                    # Remove all invalid characters
                    valid_chars = (string.ascii_letters
                                   + string.digits
                                   + string.punctuation
                                   + ' ' + '\n')
                    text_ascii = ''.join(char for char in text if char
                                         in valid_chars)
                    # Replace all groups of whitespace characters with a single
                    # space.
                    text_stripped = re.sub(r'\s+', ' ', text_ascii).strip()
                    # Count the number of words. Skip if there are too many
                    # or too few.
                    words = text_stripped.count(' ') + 1
                    if words < conf.getint('config', 'min_text_words'):
                        continue
                    if words > conf.getint('config', 'max_text_words'):
                        continue
                    # Find size of second character in the string.
                    # Skips the first in case there's a drop cap.
                    first_char = True
                    for text_line in element:
                        if isinstance(text_line, pdfminer.layout.LTTextLine):
                            for character in text_line:
                                if isinstance(character,
                                              pdfminer.layout.LTChar):
                                    char_size = int(character.size)
                                    if not first_char:
                                        break
                                    first_char = False
                            break
                    text_chunks.append(text_stripped)
                    text_sizes.append(char_size)

    # Construct query
    threshold_size = max(text_sizes)
    query = ''
    for chunk, size in zip(text_chunks, text_sizes):
        if size >= threshold_size:
            if len(query + ' ' + chunk) <= conf.getint('config',
                                                       'max_query_chars'):
                query += (' ' + chunk)
    query = query.strip()

    # Send Query
    print(termcolor.colored('Querying Crossref with:', 'yellow'))
    print(f'`{query}`')
    cr = habanero.Crossref()
    result = cr.works(query_bibliographic=query,
                      limit=conf.getint('config', 'max_query_results'))

    # Print results
    print()
    print(termcolor.colored('Crossref query results:', 'yellow'))
    for i in range(conf.getint('config', 'max_query_results')):
        title = result['message']['items'][i].get('title', [''])[0]
        authors = result['message']['items'][i].get('author', '')
        author_name_list = []
        for entry in authors:
            author_name_list.append(entry['family'] + ', ' + entry['given'])
        author_names = '; '.join(author_name_list)
        doi = result['message']['items'][i].get('DOI', '')
        pub = result['message']['items'][i].get('publisher', '')
        print(termcolor.colored(f'{i+1}. {title}', 'white', attrs=['bold']))
        if author_names != '':
            print(f"   {author_names}")
        if pub != '':
            print(f"   {pub}")
        if doi != '':
            print(f"   {doi}")

    print()
    while True:
        try:
            selected_result = int(input(termcolor.colored('Select a result: ',
                                                          'yellow'))) - 1
            if selected_result < 0:
                raise ValueError
            if selected_result >= conf.getint('config', 'max_query_results'):
                raise ValueError
        except ValueError:
            continue
        else:
            break

    bib_entry = habanero.cn.content_negotiation(
        ids=result['message']['items'][selected_result]['DOI'],
        format='bibentry')

    print()
    print(termcolor.colored('BibTeX entry:', 'yellow'))
    print(bib_entry)

    print()
    print(termcolor.colored('BibTeX entry copied to clipboard.', 'yellow'))
    pyperclip.copy(bib_entry)
