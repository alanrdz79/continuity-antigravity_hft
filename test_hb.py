import asyncio
from conectores.matchbook_async import MatchbookClientAsync
async def test():
    client = MatchbookClientAsync()
    await client.init_session()
    print('session', await client.get_session())
    res = await client.session.post(client.BASE_URL + '/v1/heartbeat', json={'timeout': 30}, timeout=5)
    print('POST heartbeat:', res.status_code, res.text)
    res2 = await client.session.get(client.AUTH_URL, timeout=5)
    print('GET auth_url:', res2.status_code, res2.text)
    await client.cerrar_sesion()
asyncio.run(test())
