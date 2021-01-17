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
import arxiv


class CrossrefResult():
    def __init__(self, title, authors, publisher, doi):
        self.title = title
        self.authors = authors
        self.publisher = publisher
        self.doi = doi
        self._bibtex = None

    def get_itemize(self, prefix):
        string = f"{prefix}{self.title}"
        if self.authors != '':
            string += f"\n{' '*len(prefix)}{self.authors}"
        if self.publisher != '':
            string += f"\n{' '*len(prefix)}{self.publisher}"
        if self.doi != '':
            string += f"\n{' '*len(prefix)}{self.doi}"
        return string

    def get_bibtex(self, force_update=False):
        if (self._bibtex is None) or force_update:
            if self.doi != '':
                self._bibtex = habanero.cn.content_negotiation(
                    ids=self.doi, format='bibentry')
            else:
                self._bibtex = None
                # TODO Use logger here
                print('No DOI, could not fetch bibtex')
        return self._bibtex


class ArxivResult():
    def __init__(self):
        pass

    def get_itemize(self, prefix):
        pass

    def get_bibtex(self, force_update=False):
        pass


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

    # Set up arguments
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

    # Build a query from a PDF file
    query = construct_query_from_pdf(args.file, conf)

    # Send Query
    results = query_crossref(query, conf)
    # res = arxiv.query(query=query, max_results=20)

    if len(results) == 0:
        # TODO use logger
        print('No results found')
        # TODO System exit?
        return

    # Print results
    _print_section('Query results:')
    for i, res in enumerate(results):
        print(res.get_itemize(f'{i+1}. '))

    # Select a result
    selected_result = _prompt_result_selection(
        conf.getint('config', 'max_query_results'))
    bib_entry = results[selected_result].get_bibtex()

    # Print selected entry
    _print_section('BibTeX entry:')
    print(bib_entry)

    # Copy entry to clipboard
    _print_section('BibTeX entry copied to clipboard.')
    pyperclip.copy(bib_entry)


def construct_query_from_pdf(file, conf):
    # Extract relevant text chunks and their font sizes
    text_chunks = []
    text_sizes = []
    for page_layout in pdfminer.high_level.extract_pages(
            file, maxpages=conf.getint('config', 'max_pages')):
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
    return query.strip()


def query_crossref(query, conf):
    _print_section('Querying Crossref with:')
    print(f'`{query}`')
    crossref = habanero.Crossref()
    result = crossref.works(query_bibliographic=query,
                            limit=conf.getint('config', 'max_query_results'))
    if len(result['message']['items']) == 0:
        # Logging here
        print('No results from Crossref')
        return []
    results = []
    for i in range(conf.getint('config', 'max_query_results')):
        # Get metadata
        title = result['message']['items'][i].get('title', [''])[0]
        authors = result['message']['items'][i].get('author', '')
        doi = result['message']['items'][i].get('DOI', '')
        pub = result['message']['items'][i].get('publisher', '')
        # Format author names
        author_name_list = []
        for entry in authors:
            author_name_list.append(entry['given'] + ' ' + entry['family'])
        author_names = ' and '.join(author_name_list)
        # Create CrossrefResult object
        results.append(CrossrefResult(title, author_names, pub, doi))
    return results


def query_arxiv():
    pass


def _print_section(text):
    print(termcolor.colored(text, 'yellow'))


def _prompt_result_selection(max_query_results):
    while True:
        try:
            selected_result = int(input(termcolor.colored('Select a result: ',
                                                          'yellow'))) - 1
            if selected_result < 0:
                raise ValueError
            if selected_result >= max_query_results:
                raise ValueError
        except ValueError:
            continue
        else:
            break
    return selected_result
