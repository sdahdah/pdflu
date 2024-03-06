# pdflu

Command line tool to find BibTeX entries from PDFs using Crossref and arXiv.

Very much a work-in-progress right now.

## Usage

```
Usage: pdflu [OPTIONS] FILE

  Lookup BibTeX from PDF.

Options:
  --verbose          Print detailed output.
  --debug            Print debug information.
  -c, --config FILE  Specify configuration file.
  -i, --interactive  Run an interactive query.
  --help             Show this message and exit.
```

## Configuration

Place the following file in`~/.config/pdflu/pdflu.conf`:

```ini
[pdflu]
# Maximum number of query results to fetch (per API)
max_query_results = 10
# Put an email here to gain access to the Crossref API's polite pool, which
# gives better performance. For more info, see
# https://github.com/CrossRef/rest-api-doc#good-manners--more-reliable-service
polite_pool_email = you@email.com

[parsing]
# Maximum number of pages to parse
max_pages = 2
# Maximum number of lines for text box to be parsed
max_lines = 4
# Minimum number of words for text box to be parsed
min_words = 2
# Maximum number of words for text box to be parsed
max_words = 30
# Maximum number of characters in a query
max_chars = 200

# vi: ft=conf
```

