from argparse import ArgumentParser
from pathlib import Path
from re import compile as re_compile
from typing import Iterable, Literal

try:
    from bs4 import BeautifulSoup
except ImportError:
    print(f'Missing required packages - execute "pipenv install"')
    exit(1)

# Create ArgumentParser object and arguments
parser = ArgumentParser(description='TPDb Collection Maker')
parser.add_argument(
    'html',
    type=Path,
    metavar='HTML_FILE',
    help='File with TPDb Collection page HTML to scrape')
parser.add_argument(
    '--always-quote',
    action='store_true',
    help='Whether to put all titles in quotes ("")')


class Content:

    """Poster URL format for all TPDb posters"""
    POSTER_URL = 'https://theposterdb.com/api/assets/{id}'

    """Regex to match yearless titles and season names from full titles"""
    YEARLESS_REGEX = re_compile(r'^(.*) \(\d+\)($| - (Season \d+)|(Specials))')
    SEASON_REGEX = re_compile(r'^.* - (?:Season (\d+)|(Specials))$')

    __slots__ = (
        'poster_id', 'content_type', 'title', 'use_year', 'must_quote', 'url',
        'yearless_title', 'season_number', 'sub_content',    
    )

    def __init__(self, poster_id: int,
                 content_type: Literal['Collection', 'Show', 'Movie'],
                 title: str, *, must_quote: bool=False) -> None:

        self.poster_id = poster_id
        self.content_type = content_type
        self.title = title
        self.use_year = False
        self.must_quote = must_quote or ': ' in self.title
        self.url = self.POSTER_URL.format(id=self.poster_id)

        # Attempt to parse the yearless title
        if (group := self.YEARLESS_REGEX.match(self.title)) is None:
            self.yearless_title = self.title
        else:
            self.yearless_title = group.group(1)

        # If season name is in the title, parse 
        if (season_group := self.SEASON_REGEX.match(self.title)) is None:
            self.season_number = None
        else:
            self.content_type = 'Season'
            if season_group.group(2) == 'Specials':
                self.season_number = 0
            else:
                self.season_number = int(season_group.group(1))

        # No subcontent yet
        self.sub_content = {}


    @property
    def final_title(self) -> str:
        """
        Get the finalized title for this Content. Quoted and utilizing the year
        if necessary.
        """

        title = self.title if self.use_year else self.yearless_title
        return f'"{title}"' if self.must_quote else title


    def __repr__(self) -> str:
        attributes = ', '.join(f'{attr}={getattr(self, attr)!r}'
                               for attr in self.__slots__
                               if not attr.startswith('__'))

        return f'<Content {attributes}>'


    def __str__(self) -> str:
        if self.content_type in ('Collection', 'Movie'):
            return f'{self.final_title}:\n  url_poster: {self.url}'
        elif self.content_type == 'Show':
            base = f'{self.final_title}:\n  url_poster: {self.url}'
            if len(self.sub_content) > 0:
                sub = '\n    '.join(str(self.sub_content[season])
                                    for season in sorted(self.sub_content))
                return f'{base}\n  seasons:\n    {sub}'
            
            return base
        elif self.content_type == 'Season':
            return f'{self.season_number}: ' + '{url_poster: ' + self.url + '}'
        else:
            return f'<Bad content type "{self.content_type}">'


    def is_sub_content_of(self, content: 'Content') -> bool:
        if self.content_type != 'Season' or content.content_type != 'Show':
            return False

        return (content.yearless_title == self.yearless_title
                and content.title in self.title)

    
    def is_parent_content_of(self, content: 'Content') -> bool:
        return content.is_sub_content_of(self)


    def add_sub_content(self, content: 'Content') -> None:
        self.sub_content[content.season_number] = content


class ContentList:
    def __init__(self) -> None:
        self.content: dict[str, Iterable[Content]] = {
            'Collection': [],
            'Movie': [],
            'Show': [],
            'Season': [],
        }

    def add_content(self, new: Content) -> None:
        # print(f'ADDING {new!r}')
        # Check if new content belongs to any existing shows
        for existing in self.content['Show']:
            if new.is_sub_content_of(existing):
                existing.add_sub_content(new)
                # Can only belong to one show, stop looping
                break

        # Check if any existing seasons belong to new content
        for existing in self.content['Season']:
            if new.is_parent_content_of(existing):
                # print(f'{new!r} is parent content of {existing!r}\n')
                new.add_sub_content(existing)

        # Check for content of this same title
        for existing in self.content[new.content_type]:
            if existing.title == new.title:
                new.use_year = True
                break

        self.content[new.content_type].append(new)

    def print(self) -> None:
        # Print each content group
        for content_type, content_list in self.content.items():
            # Don't print empty content sets, or base seasons
            if len(content_list) == 0 or content_type == 'Season':
                continue

            # Print divider, content type header, and all content
            print(f'# {"-"*80}\n# {content_type}s')
            for content in content_list:
                print(str(content))

"""If file is entrypoint, parse args"""
if __name__ == '__main__':
    # Parse given arguments
    args = parser.parse_args()

    # Get page HTML from file if provided
    if not args.html.exists():
        print(f'File "{args.html_file.resolve()}" does not exist')
        exit(1)

    # Open file and read content
    with args.html.open('r') as file_handle:
        html = file_handle.read()

    # Create BeautifulSoup element of HTML
    webpage = BeautifulSoup(html, 'html.parser')

    # Get all posters in this set, classify by content type
    content_list = ContentList()
    for poster_element in webpage.find_all('div', class_='overlay rounded-poster'):

        # Create Content object
        content_list.add_content(
            Content(
                poster_element.attrs['data-poster-id'],
                poster_element.attrs['data-poster-type'],
                poster_element.find('p', class_='p-0 mb-1 text-break').string,
                must_quote=args.always_quote,
            )
        )

    content_list.print()