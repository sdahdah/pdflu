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
import signal
import subprocess
import abc


def signal_handler(sig, frame):
    """Signal handler to catch ^C nicely."""
    print('\nInterrupt signal received\n')
    sys.exit(130)


def main():
    """Main entry point."""

    # Register signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Figure out config path using environment variables.
    # Respects the XDG Base Directory specification on Linux.
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
    parser.add_argument('-i', '--interactive', action='store_true',
                        dest='interactive', help='use interactive mode')
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
    if args.interactive:
        print(_header('Parsing PDF...'))
    query = construct_query_from_pdf(args.file, conf)

    # Send Query
    if args.interactive:
        print(_header('Querying Crossref and arXiv with:'))
        print(f'  "{query}"')
    results_crossref = query_crossref(query, conf)
    results_arxiv = query_arxiv(query, conf)
    results_combined = results_crossref + results_arxiv

    # Find number of words from query in title
    common_words = []
    query_words = query.split(' ')
    for res in results_combined:
        count = 0
        title_words = res.title.split(' ')
        for word in query_words:
            if word in title_words:
                count += 1
        common_words.append(count)
    # Sort by number of words from query in title
    results_sorted = [res for _, res in sorted(
        zip(common_words, results_combined),
        key=lambda pair: pair[0],
        reverse=True)]
    # Truncate sorted results list
    results = results_sorted[:conf.getint('pdflu', 'disp_query_results')]

    if len(results) == 0:
        print(_header('No results found'))
        sys.exit(0)

    if args.interactive:
        print(_header('Best query result:'))
        print(results[0].get_itemize('  - '))
        valid_responses = ['', 'y', 'n', '?', 'q']
        while True:
            response = _prompt('Accept? [Y/n/?/q] ', valid_responses)
            if response in ['', 'y']:
                selected_result = 0
                break
            elif response == '?':
                print('  y  yes  (default)')
                print('  n  no')
                print('  ?  help')
                print('  q  quit')
            elif response == 'q':
                sys.exit(0)
            else:
                # Print results
                max_chars = len(conf['pdflu']['disp_query_results'])
                print(_header('All query results:'))
                for i, res in enumerate(results):
                    num_chars = len(str(i + 1))
                    print(res.get_itemize(
                        f"  {' ' * (max_chars - num_chars)}{i + 1}. "))

                # Select a result
                last_result = conf.getint('pdflu', 'disp_query_results')
                valid_responses = ([str(i) for i in range(1, last_result+1)]
                                   + ['', 's', 'o', '?', 'q'])
                while True:
                    response = _prompt(
                        f'Select a result: [1-{last_result}/s/o/?/q] ',
                        valid_responses)
                    if response == '':
                        selected_result = 0
                        break
                    elif response == 's':
                        lines = conf.getint('pdflu', 'show_first_lines')
                        raw_text = pdfminer.high_level.extract_text(
                                args.file, maxpages=1)
                        text = '  ' + '\n  '.join(raw_text.split('\n')[:lines])
                        print(text)
                    elif response == 'o':
                        if os.name == 'posix':
                            subprocess.call(["xdg-open", args.file])
                        else:
                            logging.warning('Opening PDF not supported on '
                                            'Windows.')
                    elif response == '?':
                        numbers = f'1-{last_result}'
                        padding = len(numbers) - 1
                        print(f"  {numbers}  entry to select (default: 1)")
                        print(f"{' '*padding}  s  show first lines of PDF")
                        print(f"{' '*padding}  o  open PDF (Linux only)")
                        print(f"{' '*padding}  ?  help")
                        print(f"{' '*padding}  q  quit")
                    elif response == 'q':
                        sys.exit(0)
                    else:
                        selected_result = int(response) - 1
                        break
                break
    else:
        selected_result = 0

    bib_entry = results[selected_result].get_bibtex()

    # Print selected entry
    if args.interactive:
        print(_header('BibTeX entry:'))
    print(bib_entry)

    # Copy entry to clipboard
    if conf.getboolean('pdflu', 'use_clipboard'):
        if args.interactive:
            print(_header('Copying BibTeX entry to clipboard...'))
        pyperclip.copy(bib_entry)


class SearchResult(metaclass=abc.ABCMeta):
    """Object to store a search result."""

    @abc.abstractmethod
    def get_itemize(self, prefix):
        """Get a string that can be used when listing results.

        For example, if the prefix is '- ', the result is:

        - Title [Crossref/arXiv]
          Authors
          Publisher

        Parameters
        ----------
        prefix : str
            Prefix appended to beginning of first line. Usually a bullet point
            or a number. Other lines have whitespace padded in front of them
            to left-align the text.

        Returns
        -------
        str
            String used to represent result in a list.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def get_bibtex(self, force_update=False):
        """Get the bibtex entry of a result.

        For CrossrefResult objects, the BibTeX entry is fetched from the
        Crossref API. For ArxivResult objects, the BibTeX entry is fetched
        from the Crossref API if it has a DOI. Otherwise it is formatted
        manually using metadata from arXiv.

        Parameters
        ----------
        force_update : bool
            Force method to fetch entry from Crossref (if DOI is present). If
            False, result will only be fetched the first time this method is
            called. Subsequent calls will return the saved entry.

        Returns
        -------
        str
            BibTeX entry.
        """
        raise NotImplementedError()


class CrossrefResult(SearchResult):
    """Object to store a search result from Crossref."""

    def __init__(self, title, authors, publisher, doi):
        """Constructor for CrossrefResult object.

        Parameters
        ----------
        title : str
            Result title.
        authors : list[str]
            Result authors in format "First Middle von Last".
        publisher : str
            Result publisher.
        doi : str
            Result DOI.
        """
        self.title = title
        self.authors = ' and '.join(authors)
        self.publisher = publisher
        self.doi = doi
        self._bibtex = None

    def get_itemize(self, prefix):
        """See SearchResult documentation."""
        string = (termcolor.colored(f'{prefix}{self.title} ',
                                    'yellow', attrs=['bold'])
                  + termcolor.colored('[Crossref]', 'yellow', attrs=['bold']))
        if self.authors != '':
            string += f"\n{' '*len(prefix)}{self.authors}"
        third_line = []
        if self.publisher != '':
            third_line.append(self.publisher)
        if self.doi != '':
            third_line.append(self.doi)
        if len(third_line) != 0:
            string += f"\n{' '*len(prefix)}{', '.join(third_line)}"
        return string

    def get_bibtex(self, force_update=False):
        """See SearchResult documentation."""
        if (self._bibtex is None) or force_update:
            if self.doi != '':
                result = habanero.cn.content_negotiation(ids=self.doi,
                                                         format='bibentry')
                self._bibtex = re.sub(r'\t', '    ', result)
            else:
                self._bibtex = None
                logging.warning('DOI empty for result `{self}`. Could not '
                                'fetch BibTeX entry.')
        return self._bibtex


class ArxivResult(SearchResult):
    """Object to store a search result from arXiv."""

    def __init__(self, title, authors, year, url, category, doi=None):
        """Constructor for ArxivResult object.

        Parameters
        ----------
        title : str
            Result title.
        authors : list[str]
            Result authors in format "First Middle von Last".
        year : str
            Result publication year.
        url : str
            Result URL.
        category :
            Result primary category (e.g., "cs.SY")
        doi : str
            Result DOI if available.
        """
        self.title = title
        self.authors = ' and '.join(authors)
        self.year = year
        self.id = url.split('/')[-1]
        self.category = category
        # Generate BibTeX key
        key_items = []
        if len(authors) != 0:
            key_items.append(authors[0].split(' ')[-1].lower())
        if year != '':
            key_items.append(year)
        key_items.append(f"{self.title.split(' ')[0]}".lower())
        self.key = '_'.join(key_items)
        self.doi = doi
        self._bibtex = None

    def get_itemize(self, prefix):
        """See SearchResult documentation."""
        string = (termcolor.colored(f'{prefix}{self.title} ',
                                    'red', attrs=['bold'])
                  + termcolor.colored('[arXiv]', 'red', attrs=['bold']))
        if self.authors != '':
            string += f"\n{' '*len(prefix)}{self.authors}"
        third_line = []
        if (self.id != '' and self.category != ''):
            third_line.append(f"{self.id} [{self.category}]")
        if self.doi is not None:
            third_line.append(self.doi)
        if len(third_line) != 0:
            string += f"\n{' '*len(prefix)}{', '.join(third_line)}"
        return string

    def get_bibtex(self, force_update=False):
        """See SearchResult documentation."""
        if self.doi is None:
            string = f'@misc{{{self.key},'
            string += f'\n    title={{{self.title}}},'
            if self.authors != '':
                string += f'\n    author={{{self.authors}}},'
            if self.year != '':
                string += f'\n    year={{{self.year}}},'
            if self.id != '':
                string += f'\n    eprint={{{{{self.id}}}}},'
            string += '\n    archivePrefix={{arXiv}},'
            if self.category != '':
                string += f'\n    primaryClass={{{{{self.category}}}}},'
            string += '\n}'
            self._bibtex = string
        elif (self._bibtex is None) or force_update:
            if self.doi != '':
                result = habanero.cn.content_negotiation(ids=self.doi,
                                                         format='bibentry')
                self._bibtex = re.sub(r'\t', '    ', result)
            else:
                self._bibtex = None
                logging.warning('DOI empty for result `{self}`. Could not '
                                'fetch BibTeX entry.')
        return self._bibtex


def construct_query_from_pdf(file, conf):
    """Construct a search query from a PDF file.

    Uses a few different heuristics to try to build a good query.

    Rough summary:

    1. Parses up to a set number of PDF pages.
    2. Breaks the PDF into text boxes.
    3. Strips away unwanted characters and whitespace.
    4. Throws out text boxes that are too long or too short.
    5. Throws out text boxes with small font sizes. Currently only picks the
       ones with the largest font size.
    6. Concatenates the text boxes to form a query.
    7. Truncates the query.

    Parameters
    ----------
    file : str
        File name.
    conf : configparser.ConfigParser
        Parsed config file.

    Returns
    -------
    str :
        Search query.
    """
    # Extract relevant text chunks and their font sizes
    text_chunks = []
    text_sizes = []
    for page_layout in pdfminer.high_level.extract_pages(
            file, maxpages=conf.getint('pdflu', 'max_pages')):
        for element in page_layout:
            if isinstance(element, pdfminer.layout.LTTextContainer):
                text = element.get_text()
                lines = text.count('\n')
                if lines > conf.getint('pdflu', 'max_text_lines'):
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
                    if words < conf.getint('pdflu', 'min_text_words'):
                        continue
                    if words > conf.getint('pdflu', 'max_text_words'):
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
    # Throw out text boxes with font size under the threshold. Build query.
    # Threshold is current just the max size
    threshold_size = max(text_sizes)
    query = ''
    for chunk, size in zip(text_chunks, text_sizes):
        if size >= threshold_size:
            if len(query + ' ' + chunk) <= conf.getint('pdflu',
                                                       'max_query_chars'):
                query += (' ' + chunk)
    return query.strip()


def query_crossref(query, conf):
    """Send Crossref a query and return a list of results.

    Be sure to add an email to your config to be part of the Crossref polite
    pool.

    Parameters
    ----------
    query : str
        Query string.
    conf : configparser.ConfigParser
        Parsed config file.

    Returns
    -------
    list[CrossrefResult]
        List of results.
    """
    polite_pool_email = conf['pdflu'].get('polite_pool_email', None)
    if polite_pool_email is None:
        logging.warning('To gain access to the Crossref polite pool, add an '
                        'email')
    crossref = habanero.Crossref(mailto=polite_pool_email)
    result = crossref.works(query_bibliographic=query,
                            limit=conf.getint('pdflu', 'max_query_results'))
    if len(result['message']['items']) == 0:
        # Logging here
        print('No results from Crossref')
        return []
    results = []
    for i in range(conf.getint('pdflu', 'max_query_results')):
        # Get metadata
        title = result['message']['items'][i].get('title', [''])[0]
        authors = result['message']['items'][i].get('author', '')
        doi = result['message']['items'][i].get('DOI', '')
        pub = result['message']['items'][i].get('publisher', '')
        # Format author names
        author_names = []
        for entry in authors:
            name_parts = []
            given = entry.get('given', '')
            family = entry.get('family', '')
            if given != '':
                name_parts.append(given)
            if family != '':
                name_parts.append(family)
            author_names.append(' '.join(name_parts))
        # Create CrossrefResult object
        results.append(CrossrefResult(title, author_names, pub, doi))
    return results


def query_arxiv(query, conf):
    """Send arXiv a query and return a list of results.

    Parameters
    ----------
    query : str
        Query string.
    conf : configparser.ConfigParser
        Parsed config file.

    Returns
    -------
    list[ArxivResult]
        List of results.
    """
    result = arxiv.query(
        query=query, max_results=conf.getint('pdflu', 'max_query_results'))
    if len(result) == 0:
        # Logging here
        print('No results from arXiv')
        return []
    results = []
    for i in range(conf.getint('pdflu', 'max_query_results')):
        title = re.sub(r'\s+', ' ', result[i]['title'])
        authors = result[i]['authors']
        year = str(result[i]['published_parsed'].tm_year)
        url = result[i]['id']
        category = result[i]['arxiv_primary_category']['term']
        doi = result[i]['doi']
        results.append(ArxivResult(title, authors, year, url, category, doi))
    return results


def _header(string):
    """Format a string as a header.

    Style inspired by pacman.

    Parameters
    ----------
    string : str
        String to format

    Returns
    -------
    str
        String formatted as header
    """
    return (termcolor.colored('::', 'blue', attrs=['bold'])
            + termcolor.colored(f' {string}', 'white', attrs=['bold']))


def _prompt(prompt, valid_responses):
    """Prompt the user for input. Loop until valid string is input.

    Parameters
    ----------
    prompt : str
        User prompt.
    valid_responses : list[str]
        Lowercase list of valid input strings.

    Returns
    -------
    string
        User's (valid) response.
    """
    while True:
        response = input(_header(prompt))
        if response.lower() in valid_responses:
            return response.lower()
