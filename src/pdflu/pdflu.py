"""Command line tool to find BibTeX for papers using Crossref and arXiv."""

import configparser
import logging
import os
import pathlib
from typing import Optional, Sequence

import bibtexparser
import click

from . import parse, search, utilities

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


@click.group()
@click.option('--verbose', is_flag=True, help='Print detailed output.')
@click.option('--debug', is_flag=True, help='Print debug information.')
@click.option(
    '-c',
    '--config',
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help='Specify configuration file.',
)
@click.pass_context
def cli(ctx, verbose, debug, config):
    """Manage BibTeX references."""
    # Set logging level
    if debug:
        logging_level = logging.DEBUG
        formatter = '[%(asctime)s] %(levelname)s: %(message)s'
    elif verbose:
        logging_level = logging.INFO
        formatter = '%(levelname)s: %(message)s'
    else:
        logging_level = logging.WARNING
        formatter = '%(levelname)s: %(message)s'
    logging.basicConfig(format=formatter, level=logging_level)
    # Parse config
    conf = configparser.ConfigParser()
    conf['DEFAULT'] = {
        'field_order': ('title, author, month, year, booktitle, journaltitle, '
                        'eventtitle, journal, publisher, location, series, '
                        'volume, number, pages, numpages, issn, doi, url, '
                        'groups, keywords, comment, file'),
        'max_query_results':
        10,
        'polite_pool_email':
        '',
        'max_pages':
        2,
        'max_lines':
        4,
        'min_words':
        2,
        'max_words':
        30,
        'max_chars':
        200,
    }
    conf.read(_get_default_config_path() if config is None else config)
    ctx.obj = {
        'config': conf,
    }


@cli.command()
@click.argument(
    'file',
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
)
@click.option(
    '-q',
    '--query',
    type=str,
    default=None,
    help='Manually specified query. Only supported when adding one file.',
)
@click.option(
    '-i',
    '--interactive',
    is_flag=True,
    help='Run an interactive query.',
)
@click.pass_obj
def lookup(obj, file, query, interactive):
    """Add linked files to BibTeX library."""
    config = obj['config']
    if query:
        entries = _query_string(
            query,
            limit=config.getint('pdflu', 'max_query_results'),
            mailto=config.get('pdflu', 'polite_pool_email'),
        )
    else:
        # Get metadata
        metadata = parse.parse_pdf(
            file,
            max_pages=config.getint('parsing', 'max_pages'),
            max_lines=config.getint('parsing', 'max_lines'),
            min_words=config.getint('parsing', 'min_words'),
            max_words=config.getint('parsing', 'max_words'),
            max_chars=config.getint('parsing', 'max_chars'),
        )
        if interactive:
            print('Metadata')
            print('--------')
            print(metadata)
            print()
        # Query online based on metadata
        entries = _query_file(
            metadata,
            limit=config.getint('pdflu', 'max_query_results'),
            mailto=config.get('pdflu', 'polite_pool_email'),
        )
        sel = 0
        if interactive:
            print('Results')
            print('-------')
            for (k, result) in enumerate(entries):
                result_str = str(result).replace('\n', '\n    ')
                print(f'[{k}] {result_str}')
            print('[q] quit')
            sel_str = click.prompt('Selection', default='0')
            print()
            if sel_str == 'q':
                return
            else:
                sel = int(sel_str)
        if entries:
            if (len(entries) > 1) and (sel < len(entries)) and interactive:
                selected_entry = entries[sel].get_entry()
            else:
                selected_entry = entries[0].get_entry()
        db = bibtexparser.Library()
        db.add(selected_entry)
        bibtex_format = bibtexparser.BibtexFormat()
        bibtex_format.indent = '    '
        bibtex_format.block_separator = '\n'
        bibtex_format.trailing_comma = True
        bib_str = bibtexparser.write_string(
            db,
            prepend_middleware=[
                bibtexparser.middlewares.MergeNameParts(),
                bibtexparser.middlewares.MergeCoAuthors(),
                bibtexparser.middlewares.SortFieldsCustomMiddleware(
                    order=config.get('pdflu', 'field_order').split(', ')),
            ],
            bibtex_format=bibtex_format,
        )
        print('BibTeX')
        print('------')
        print(bib_str)


def _query_file(
    metadata: parse.Metadata,
    limit: int = 10,
    mailto: Optional[str] = None,
) -> Sequence[search.SearchResult]:
    """Query by file metadata."""
    if not mailto:
        log.warn('`mailto` not specified, not in Crossref polite pool.')
    # Check metadata
    if not metadata:
        return []
    # Search by DOI first
    entries: Sequence[search.SearchResult]
    if metadata.doi:
        entries = search.query_crossref_doi(metadata.doi, mailto=mailto)
        if entries:
            return entries
    # Search by arXiv ID if no DOI
    if metadata.arxiv_id:
        entries = search.query_arxiv_id(metadata.arxiv_id)
        if entries:
            return entries
    # Fall back on text query
    query_title = utilities.clean_string_for_query(metadata.title)
    query_author = utilities.clean_string_for_query(metadata.author)
    query = query_title + query_author
    ranked_entries = _query_string(query, limit=limit, mailto=mailto)
    return ranked_entries


def _query_string(
    query: str,
    limit: int = 10,
    mailto: Optional[str] = None,
) -> Sequence[search.SearchResult]:
    """Query by file."""
    if not mailto:
        log.warn('`mailto` not specified, not in Crossref polite pool.')
    entries_crossref = search.query_crossref(query, limit=limit, mailto=mailto)
    entries_arxiv = search.query_arxiv(query, limit=limit)
    entries = list(entries_crossref) + list(entries_arxiv)
    ranked_entries = search.rank_results(entries, query)
    return ranked_entries


def _get_default_config_path() -> Optional[pathlib.Path]:
    """Get default config path."""
    config_file = 'pdflu/pdflu.conf'
    if os.name == 'posix':
        # Use XDG default if specified
        xdg_config_home_raw = os.environ.get('XDG_CONFIG_HOME')
        if xdg_config_home_raw is None:
            # Use ``~/.config`` if not specified
            home = os.environ.get('HOME')
            if home is not None:
                xdg_config_home = pathlib.Path(home, '.config')
            else:
                return None
        else:
            xdg_config_home = pathlib.Path(xdg_config_home_raw)
        default_conf_path = xdg_config_home.joinpath(config_file)
    else:
        # Use ``%LOCALAPPDATA%`` if specified
        localappdata = os.environ.get('LOCALAPPDATA')
        if localappdata is not None:
            default_conf_path = pathlib.Path(localappdata, config_file)
        else:
            return None
    return default_conf_path


if __name__ == '__main__':
    cli()
