from datetime import datetime

from sqlalchemy.sql import func, select

from playlog.models import album, artist, track


ORDER_DIRECTIONS = ['asc', 'desc']
DEFAULT_ORDER_DIRECTION = 'asc'
ORDER_FIELDS = ['artist_name', 'album_name', 'track_name', 'first_play', 'last_play', 'plays']
DEFAULT_ORDER_FIELD = 'artist_name'


async def create(conn, album_id, name):
    now = datetime.utcnow()
    return await conn.scalar(track.insert().values(
        name=name,
        album_id=album_id,
        plays=1,
        first_play=now,
        last_play=now
    ))


async def find_one(conn, **kwargs):
    query = select([
        artist.c.id.label('artist_id'),
        artist.c.name.label('artist_name'),
        album.c.name.label('album_name'),
        track
    ])
    for key, value in kwargs.items():
        query = query.where(getattr(track.c, key) == value)
    query = query.select_from(track.join(album).join(artist))
    result = await conn.execute(query)
    return await result.fetchone()


async def find_many(conn, offset, limit, **kwargs):
    artist_name = artist.c.name.label('artist')
    album_name = album.c.name.label('album')

    order_field = kwargs.get('order_field', DEFAULT_ORDER_FIELD)
    if order_field == 'artist_name':
        order_expr = artist_name
    elif order_field == 'album_name':
        order_expr = album_name
    elif order_field == 'track_name':
        order_expr = track.c.name
    else:
        order_expr = getattr(track.c, order_field)
    order_direction = kwargs.get('order_direction', DEFAULT_ORDER_DIRECTION)
    order_expr = getattr(order_expr, order_direction)

    query = select([
        artist.c.id.label('artist_id'),
        artist_name,
        album_name,
        track
    ])

    if 'artist_name' in kwargs:
        query = query.where(artist_name.ilike('%{}%'.format(kwargs['artist_name'])))
    if 'album_name' in kwargs:
        query = query.where(album_name.ilike('%{}%'.format(kwargs['album_name'])))
    if 'track_name' in kwargs:
        query = query.where(track.c.name.ilike('%{}%'.format(kwargs['track_name'])))
    if 'first_play_gt' in kwargs:
        query = query.where(track.c.first_play >= kwargs['first_play_gt'])
    if 'first_play_lt' in kwargs:
        query = query.where(track.c.first_play <= kwargs['first_play_lt'])
    if 'last_play_gt' in kwargs:
        query = query.where(track.c.last_play >= kwargs['last_play_gt'])
    if 'last_play_lt' in kwargs:
        query = query.where(track.c.last_play <= kwargs['last_play_lt'])

    from_clause = track.join(album).join(artist)

    total = await conn.scalar(
        query.select_from(from_clause)
             .with_only_columns([func.count(track.c.id)])
    )

    query = query.offset(offset).limit(limit).order_by(order_expr())
    query = query.select_from(from_clause)

    result = await conn.execute(query)
    items = await result.fetchall()

    return {'items': items, 'total': total}


async def find_for_album(conn, album_id):
    query = select([track]).where(track.c.album_id == album_id).order_by(track.c.plays.desc())
    result = await conn.execute(query)
    return await result.fetchall()


async def update(conn, track_id):
    await conn.execute(track.update().values(
        plays=track.c.plays + 1,
        last_play=datetime.utcnow()
    ).where(track.c.id == track_id))


async def count_total(conn):
    return await conn.scalar(track.count())


async def count_new(conn, since):
    return await conn.scalar(select([func.count()]).where(track.c.first_play >= since))