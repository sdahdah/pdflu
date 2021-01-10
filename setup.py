import setuptools

with open('README.md', 'r') as f:
    readme = f.read()

setuptools.setup(
    name='pdflookup',
    version='0.1.0',
    description='Command line tool to find BibTeX for academic papers using '
                'Crossref',
    long_description=readme,
    author='Steven Dahdah',
    url='https://github.com/sdahdah/pdflookup',
    packages=setuptools.find_packages(),
    entry_points={
        'console_scripts': ['pdflookup=pdflookup.pdflookup:main'],
    },
    install_requires=['habanero', 'pdftotext'],
)
