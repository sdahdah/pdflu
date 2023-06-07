import setuptools

with open('README.md', 'r') as f:
    readme = f.read()

setuptools.setup(
    name='pdflu',
    version='0.1.0',
    description='Command line tool to find BibTeX for academic papers using '
                'Crossref and arXiv.',
    long_description=readme,
    author='Steven Dahdah',
    url='https://github.com/sdahdah/pdflu',
    packages=setuptools.find_packages(),
    entry_points={
        'console_scripts': ['pdflu=pdflu.pdflu:main'],
    },
    install_requires=['habanero', 'pdfminer.six', 'termcolor', 'arxiv', 'pyperclip'],
)
