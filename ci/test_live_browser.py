#!/usr/bin/env python3
"""Real Chromium + live Android TV emulator viewer interaction test."""
import pathlib
import re
from playwright.sync_api import sync_playwright

OUT = pathlib.Path('smoke-report')
OUT.mkdir(exist_ok=True)
URL='http://127.0.0.1:6080/'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    for label,width,height in [('landscape',844,390),('portrait',390,844)]:
        context=browser.new_context(viewport={'width':width,'height':height},
                                    device_scale_factor=1)
        page=context.new_page()
        page.goto(URL,wait_until='domcontentloaded',timeout=20000)
        page.locator('#inputStatus').get_by_text(re.compile('Remote: ready')).wait_for(timeout=20000)
        toggle=page.locator('#theaterToggle')
        assert toggle.get_attribute('aria-pressed') == 'false'
        toggle.click(timeout=10000)
        page.locator('body.theater-active').wait_for(timeout=6000)
        assert toggle.get_attribute('aria-pressed') == 'true'
        assert page.locator('#theaterRemote').is_visible()
        for key in ['up','down','left','right','ok','back','home']:
            assert page.locator('#theaterRemote button[data-key="'+key+'"]').is_visible(),key
        # Drag via the handle, not over remote keys. The rotated iOS portrait
        # layout must translate pointer movement to stage coordinates.
        handle=page.locator('#theaterRemoteHandle')
        assert handle.is_visible()
        before=page.locator('#theaterRemote').bounding_box()
        grip=handle.bounding_box()
        sx=grip['x']+grip['width']/2
        sy=grip['y']+grip['height']/2
        page.mouse.move(sx,sy)
        page.mouse.down()
        page.mouse.move(sx-90,sy-60,steps=5)
        page.mouse.up()
        after=page.locator('#theaterRemote').bounding_box()
        displacement=abs(after['x']-before['x'])+abs(after['y']-before['y'])
        assert displacement>15,('drag did not move',label,before,after)
        assert after['x']>=-2 and after['y']>=-2,('remote escaped viewport',label,after)
        assert after['x']+after['width']<=width+2,('remote exceeds width',label,after)
        assert after['y']+after['height']<=height+2,('remote exceeds height',label,after)
        print('PASS: draggable remote',label,'moved px',round(displacement,1))
        page.screenshot(path=str(OUT/('tvsync-live-chrome-'+label+'.png')))
        # This must reach the actual emulator, not merely change a browser label.
        page.locator('#inputStatus').get_by_text(re.compile('Remote: ready')).wait_for(timeout=5000)
        page.locator('#theaterRemote button[data-key="down"]').click(timeout=8000)
        page.locator('#inputStatus').get_by_text(re.compile(r'Remote: \d+ms device')).wait_for(timeout=10000)
        toggle.click(timeout=10000)
        assert toggle.get_attribute('aria-pressed') == 'false'
        assert not page.locator('#theaterRemote').is_visible()
        assert 'theater-active' not in (page.locator('body').get_attribute('class') or '')
        print('PASS: Chromium',label,width,height,'fullscreen, remote, Android ACK, exit')
        context.close()
    browser.close()
