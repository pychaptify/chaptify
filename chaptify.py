import argparse
import base64
import os
import sys
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv


class SpotifyAudiobookManager:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: str = '',
        ffmpeg_dir: str = ''
    ) -> None:
        """
        Initializes the SpotifyAudiobookManager with API credentials.

        Args:
            client_id (str): Spotify API client ID.
            client_secret (str): Spotify API client secret.
            access_token (str, optional): Existing Spotify API access token. Defaults to ''.
            ffmpeg_dir (str, optional): Directory path where ffmpeg is located. Defaults to './'.
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.base_url = "https://api.spotify.com/v1"
        self.ffmpeg_dir = ffmpeg_dir
        if not self.access_token:
            self.get_api_token()

    def get_api_token(self) -> None:
        """
        Fetches a new Spotify API access token using client credentials flow.
        """
        auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        token_url = 'https://accounts.spotify.com/api/token'
        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        data = {'grant_type': 'client_credentials'}
        response = requests.post(token_url, headers=headers, data=data)

        if response.status_code == 200:
            self.access_token = response.json().get('access_token')
        else:
            raise Exception(f"Error fetching API token: {response.status_code} {response.text}")

    def search_audiobook(
        self, title: str, author: str, limit: int = 1
    ) -> Optional[Dict[str, Any]]:
        """
        Searches for an audiobook on Spotify by title and author.

        Args:
            title (str): Title of the audiobook.
            author (str): Author of the audiobook.
            limit (int, optional): Number of results to return. Defaults to 1.

        Returns:
            Optional[Dict[str, Any]]: Dictionary containing audiobook information if found, else None.
        """
        url = f"{self.base_url}/search"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"q": f"{title} {author}", "type": "audiobook", "limit": limit}
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 401:  # Token expired
            self.get_api_token()
            return self.search_audiobook(title, author, limit)
        elif response.status_code == 200:
            items = response.json().get("audiobooks", {}).get("items", [])
            if items:
                audiobook = items[0]
                return {
                    "id": audiobook["id"],
                    "name": audiobook["name"],
                    "author": ", ".join([a["name"] for a in audiobook["authors"]]),
                    "external_url": audiobook["external_urls"]["spotify"],
                }
        return None

    def fetch_from_url(self, url: str) -> Dict[str, Any]:
        """
        Fetches JSON data from a given URL using the Spotify API.

        Args:
            url (str): The URL to fetch data from.

        Returns:
            Dict[str, Any]: JSON response from the API.

        Raises:
            Exception: If the API request fails.
        """
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error fetching data: {response.status_code} {response.text}")

    def fetch_chapter_metadata(self, audiobook_id: str) -> Dict[str, Any]:
        """
        Fetches chapter metadata for the given audiobook ID.

        Args:
            audiobook_id (str): The Spotify ID of the audiobook.

        Returns:
            Dict[str, Any]: Dictionary containing chapters metadata.

        Raises:
            Exception: If the API request fails.
        """
        url = f"{self.base_url}/audiobooks/{audiobook_id}/chapters"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            response_out = response.json()
            items = self.fetch_extra_chapters(response_out, [])
            response_out['items'] = items
            return response_out
        else:
            raise Exception(f"Error fetching chapters: {response.status_code} {response.text}")

    def fetch_extra_chapters(
        self, initial_response: Dict[str, Any], items: List[Dict[str, Any]] = []
    ) -> List[Dict[str, Any]]:
        """
        Recursively fetches all chapters if the chapters data is paginated.

        Args:
            initial_response (Dict[str, Any]): Initial API response containing chapters.
            items (List[Dict[str, Any]], optional): List to accumulate chapters. Defaults to [].

        Returns:
            List[Dict[str, Any]]: Complete list of chapters.
        """
        items += initial_response.get('items', [])
        next_url = initial_response.get('next', None)
        if next_url:
            print(f"Fetching next page: {next_url}")
            next_response = self.fetch_from_url(next_url)
            items = self.fetch_extra_chapters(next_response, items)
        return items

    def fetch_book_metadata(self, audiobook_id: str) -> Dict[str, Any]:
        """
        Fetches metadata for the given audiobook ID.

        Args:
            audiobook_id (str): The Spotify ID of the audiobook.

        Returns:
            Dict[str, Any]: Dictionary containing audiobook metadata.

        Raises:
            Exception: If the API request fails.
        """
        url = f"{self.base_url}/audiobooks/{audiobook_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(
                f"Error fetching audiobook metadata: {response.status_code} {response.text}"
            )


class MetadataManager:
    def __init__(
        self,
        spotify_manager: SpotifyAudiobookManager,
        input_file: str,
        output_file: Optional[str] = None,
        overwrite_ch: bool = False,
    ) -> None:
        """
        Initializes the MetadataManager with the input file and Spotify manager.

        Args:
            spotify_manager (SpotifyAudiobookManager): An instance of SpotifyAudiobookManager.
            input_file (str): Path to the input audiobook file.
            output_file (Optional[str], optional): Path to the output file. Defaults to None.
            overwrite_ch (bool, optional): Whether to overwrite existing chapters. Defaults to False.
        """
        self.spotify_manager = spotify_manager
        self.input_file = Path(input_file)
        self.ffmpeg_dir = spotify_manager.ffmpeg_dir
        self.metadata_path = self.input_file.parent / "FFMETADATAFILE"
        self.output_file = output_file or str(self.input_file).replace(
            ".m4b", "_chapterized.m4b"
        )
        try:
            self.dump_input_metadata(overwrite_ch)
        except Exception as e:
            print(
                f'WARNING: Error reading in {self.input_file.stem}, skipping file. Error: {e}'
            )

    def dump_input_metadata(self, overwrite_ch: bool = False) -> None:
        """
        Extracts existing metadata from the input file.

        Args:
            overwrite_ch (bool, optional): Whether to overwrite existing chapters. Defaults to False.

        Raises:
            subprocess.CalledProcessError: If ffmpeg command fails.
        """
        orig_metadata = self.input_file.parent / "FFMETADATAFILE_orig"
        command = [
            f"{self.ffmpeg_dir}ffmpeg",
            "-loglevel",
            "panic",
            "-y",
            "-i",
            str(self.input_file),
            "-f",
            "ffmetadata",
            str(self.metadata_path),
        ]
        subprocess.run(command, check=True)
        # shutil.copy(str(self.metadata_path), str(orig_metadata))
        if overwrite_ch:
            with self.metadata_path.open('r') as f:
                metadata_content = f.read()
            # Keep everything before the first [CHAPTER]
            metadata_content = metadata_content.split('[CHAPTER]', 1)[0]
            with self.metadata_path.open('w') as f:
                f.write(metadata_content)

    def generate_ffmetadata(self, chapters: List[Dict[str, Any]]) -> str:
        """
        Generates FFmpeg metadata format for chapters.

        Args:
            chapters (List[Dict[str, Any]]): List of chapter metadata.

        Returns:
            str: String containing FFmpeg metadata for chapters.
        """
        metadata = ""
        current_start = 0.0
        for chapter in chapters:
            duration = chapter["duration_ms"] / 1000.0
            current_end = current_start + duration + 0.05
            metadata += (
                "\n[CHAPTER]\n"
                "TIMEBASE=1/1000\n"
                f"START={int(current_start * 1000)}\n"
                f"END={int(current_end * 1000)}\n"
                f"title={chapter['name']}\n"
            )
            current_start = current_end
        return metadata

    def get_metadata_info(self) -> (Optional[str], Optional[str]):
        """
        Extracts title and author from metadata or filename.

        Returns:
            Tuple[Optional[str], Optional[str]]: A tuple containing author and title.
        """
        with self.metadata_path.open('r') as f:
            metadata_lines = f.readlines()
        metadata_dict = {}
        for line in metadata_lines:
            if "=" in line:
                key, value = line.strip().split("=", 1)
                metadata_dict[key] = value
        title = metadata_dict.get("title", None)
        author = metadata_dict.get("artist", None)

        if not title or not author:
            # Fallback to filename
            match = re.match(
                r"(?:\[.*?\] )?(?P<author>[^-]+) - (?P<title>.+)", self.input_file.stem
            )
            if match:
                author = author or match.group("author").strip()
                title = title or match.group("title").strip()
        return author, title

    def append_chapters(self, chapters: List[Dict[str, Any]]) -> None:
        """
        Appends chapter metadata to the input file and saves the output file.

        Args:
            chapters (List[Dict[str, Any]]): List of chapter metadata.
        """
        metadata_content = self.generate_ffmetadata(chapters)
        with self.metadata_path.open("a") as meta_file:
            meta_file.write(metadata_content)

        command = [
            f"{self.ffmpeg_dir}ffmpeg",
            "-loglevel",
            "panic",
            "-y",
            "-i",
            str(self.input_file),
            "-i",
            str(self.metadata_path),
            "-map_metadata",
            "1",
            "-map_chapters",
            "1",
            "-codec",
            "copy",
            str(self.output_file),
        ]
        print(f"Running command: {' '.join(command)}")
        subprocess.run(command, check=True)
        print(f"File updated with chapters: {self.output_file}")
        os.remove(self.metadata_path)

def process_file(
    input_file: str,
    spotify_manager: SpotifyAudiobookManager,
    output_file: Optional[str] = None,
    output_dir: Optional[str] = None,
    overwrite_ch: bool = True,
    dump_metadata_only: bool = False,
) -> None:
    """
    Processes a single audiobook file, fetches chapters from Spotify, and appends them.

    Args:
        input_file (str): Path to the input audiobook file.
        spotify_manager (SpotifyAudiobookManager): An instance of SpotifyAudiobookManager.
        output_file (Optional[str], optional): Path to the output file. Defaults to None.
        output_dir (Optional[str], optional): Directory to write the output file to. Defaults to None.
        overwrite_ch (bool, optional): Whether to overwrite existing chapters. Defaults to True.
        dump_metadata_only (bool, optional): If True, only dumps metadata and exits. Defaults to False.
    """
    input_path = Path(input_file)
    if "_chapterized" in str(input_path):
        print(f"Skipping already chapterized file: {input_file}")
        return

    if output_file:
        output_path = Path(output_file)
    else:
        output_filename = input_path.stem + "_chapterized.m4b"
        if output_dir:
            output_path = Path(output_dir) / output_filename
        else:
            output_path = input_path.parent / output_filename

    metadata_manager = MetadataManager(
        spotify_manager, str(input_path), str(output_path), overwrite_ch=overwrite_ch
    )

    if dump_metadata_only:
        return

    author, title = metadata_manager.get_metadata_info()
    if not author or not title:
        print("Could not extract author and title from metadata or filename.")
        return

    audiobook = spotify_manager.search_audiobook(title, author)
    if audiobook:
        chapters = spotify_manager.fetch_chapter_metadata(audiobook["id"])["items"]
        # Exclude the last chapter if it's a dud
        chapters_to_append = chapters[:-1] if len(chapters) > 1 else chapters
        metadata_manager.append_chapters(chapters_to_append)
    else:
        print(f"Audiobook '{title}' by '{author}' not found on Spotify.")


def main() -> None:
    """
    Main function to parse command-line arguments and process audiobook files.
    """
    if len(sys.argv) == 2: #feeling lazy, default single input is a file
        sys.argv.insert(1,'-f')
    parser = argparse.ArgumentParser(
        description="Process audiobook files with Spotify chapters."
    )
    parser.add_argument('-f', '--file', help='Input file')
    parser.add_argument('-o', '--output', help='Output file name (only valid with -f)')
    parser.add_argument('-i', help='Text file with list of input files')
    parser.add_argument('-d', '--dir', help='Directory to search for .m4b files')
    parser.add_argument('-p', '--dirout', help='Directory to write output files to')
    args = parser.parse_args()

    # Load environment variables from .env file
    load_dotenv()
    client_id = os.getenv('CLIENT_ID')
    client_secret = os.getenv('CLIENT_SECRET')
    if not client_id or not client_secret:
        raise ValueError(
            "Spotify CLIENT_ID and CLIENT_SECRET must be set in the .env file."
        )

    spotify_manager = SpotifyAudiobookManager(client_id, client_secret)

    input_files: List[str] = []

    if args.file:
        input_files.append(args.file)

    if args.i:
        list_file = Path(args.i)
        if not list_file.is_file():
            print(f"The file '{args.i}' does not exist.")
            return
        with list_file.open('r') as f:
            file_list = [line.strip() for line in f if line.strip()]
            input_files.extend(file_list)

    if args.dir:
        directory = Path(args.dir)
        if not directory.is_dir():
            print(f"The directory '{args.dir}' does not exist.")
            return
        dir_files = list(directory.glob('*.m4b'))
        input_files.extend([str(f) for f in dir_files])

    if not input_files:
        print("No input files provided. Use -f, -i, or -d to specify input files.")
        return

    if args.output and len(input_files) > 1:
        print("The -o/--output option can only be used with a single input file.")
        return

    output_dir = args.dirout or None #or os.getcwd()

    for input_file in input_files:
        output_file = args.output if args.output and len(input_files) == 1 else None
        process_file(
            input_file=input_file,
            spotify_manager=spotify_manager,
            output_file=output_file,
            output_dir=output_dir,
            overwrite_ch=True,
            dump_metadata_only=False,
        )
        

if __name__ == "__main__":
    main()
