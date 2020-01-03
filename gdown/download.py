from __future__ import print_function

import os
import os.path as osp
import re
import shutil
import sys
import tempfile

import requests
import six
import tqdm

from .parse_url import parse_url

CHUNK_SIZE = 512 * 1024  # 512KB


def get_url_from_gdrive_confirmation(contents):
    url = ''
    for line in contents.splitlines():
        m = re.search(r'href="(\/uc\?export=download[^"]+)', line)
        if m:
            url = 'https://docs.google.com' + m.groups()[0]
            url = url.replace('&amp;', '&')
            return url
        m = re.search('confirm=([^;&]+)', line)
        if m:
            confirm = m.groups()[0]
            url = re.sub(
                r'confirm=([^;&]+)', r'confirm={}'.format(confirm), url
            )
            return url
        m = re.search('"downloadUrl":"([^"]+)', line)
        if m:
            url = m.groups()[0]
            url = url.replace('\\u003d', '=')
            url = url.replace('\\u0026', '&')
            return url


# -- (CHANGED) modified function signature --
def download(url, output, quiet, proxy):
    url_origin = url
    sess = requests.session()

    # -- (ADDED) assign a proxy dictionary to the request session
    if proxy is not None:
        sess.proxies = {"http": proxy,
                        "https": proxy}
        print("Using proxy: ", proxy)

    file_id, is_download_link = parse_url(url)

    while True:

        # -- (CHANGED) cache proxy exception
        try:
            res = sess.get(url, stream=True)
        except requests.exceptions.ProxyError as err:
            print("An error has occurred using proxy %s" % proxy,
                  file=sys.stderr)
            print(str(err), file=sys.stderr)
            return

        if 'Content-Disposition' in res.headers:
            # This is the file
            break
        if not (file_id and is_download_link):
            break

        # Need to redirect with confirmation
        url = get_url_from_gdrive_confirmation(res.text)

        if url is None:
            print('Permission denied: %s' % url_origin, file=sys.stderr)
            print(
                "Maybe you need to change permission over "
                "'Anyone with the link'?",
                file=sys.stderr,
            )
            return

    if output is None:
        if file_id and is_download_link:
            m = re.search(
                'filename="(.*)"', res.headers['Content-Disposition']
            )
            output = m.groups()[0]
        else:
            output = osp.basename(url)

    output_is_path = isinstance(output, six.string_types)

    if not quiet:
        print('Downloading...')
        print('From:', url_origin)
        print('To:', osp.abspath(output) if output_is_path else output)

    if output_is_path:
        tmp_file = tempfile.mktemp(
            suffix=tempfile.template,
            prefix=osp.basename(output),
            dir=osp.dirname(output),
        )
        f = open(tmp_file, 'wb')
    else:
        tmp_file = None
        f = output

    try:
        total = res.headers.get('Content-Length')
        if total is not None:
            total = int(total)
        if not quiet:
            pbar = tqdm.tqdm(total=total, unit='B', unit_scale=True)
        for chunk in res.iter_content(chunk_size=CHUNK_SIZE):
            f.write(chunk)
            if not quiet:
                pbar.update(len(chunk))
        if not quiet:
            pbar.close()
        if tmp_file:
            f.close()
            shutil.move(tmp_file, output)
    except IOError as e:
        print(e, file=sys.stderr)
        return
    finally:
        try:
            if tmp_file:
                os.remove(tmp_file)
        except OSError:
            pass

    return output
