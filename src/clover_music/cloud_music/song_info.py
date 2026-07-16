def build_music_card_data(song_info, song_comments):
    if not isinstance(song_info, list) or not song_info:
        return None
    song = song_info[0]
    if not isinstance(song, dict):
        return None

    artists = song.get("artists") or []
    artists_name = [
        artist["name"]
        for artist in artists
        if isinstance(artist, dict) and artist.get("name")
    ]
    quality = next(
        (
            song.get(key)
            for key in ("hMusic", "mMusic", "lMusic", "bMusic")
            if isinstance(song.get(key), dict)
        ),
        {},
    )
    play_time = quality.get("playTime") or song.get("duration") or 0
    try:
        seconds = int(play_time) // 1000
    except (TypeError, ValueError):
        seconds = 0
    minutes = seconds // 60
    hours = minutes // 60

    aliases = song.get("alias") or []
    album = song.get("album") or {}
    if not isinstance(album, dict):
        album = {}
    return {
        "song_name": song.get("name") or "未知歌曲",
        "song_alias": f" - {aliases[0]}" if aliases else "",
        "song_artists": "、".join(artists_name),
        "song_imgurl": album.get("blurPicUrl") or album.get("picUrl") or "",
        "song_playTime": f"{hours}:{minutes % 60:02d}:{seconds % 60:02d}",
        "song_comments": song_comments or [],
    }
