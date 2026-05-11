from __future__ import annotations

import argparse
import asyncio
from textwrap import shorten

from app.infrastructure.providers.youtube_captions import YouTubeCaptionExtractor


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test YouTube transcript extraction (manual + auto captions).",
    )
    parser.add_argument("url", help="YouTube URL to test")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="Network timeout for extraction and caption download",
    )
    parser.add_argument(
        "--minimum-words",
        type=int,
        default=20,
        help="Minimum words required for transcript to be considered usable",
    )
    args = parser.parse_args()

    extractor = YouTubeCaptionExtractor(
        timeout_seconds=args.timeout_seconds,
        minimum_words=args.minimum_words,
    )
    transcript = await extractor.extract_transcript(args.url)

    if not transcript:
        print("No usable transcript was returned.")
        print(
            "Possible reasons: captions disabled, region restriction, "
            "auto-captions unavailable, or transcript below quality threshold.",
        )
        return

    words = transcript.split()
    print("Transcript extracted successfully.")
    print(f"Word count: {len(words)}")
    print("Preview:")
    print(shorten(transcript, width=600, placeholder=" ..."))


if __name__ == "__main__":
    asyncio.run(main())
