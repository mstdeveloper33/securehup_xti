"""Reviewed immutable release archives; no implicit latest-version upgrade."""
VERSION = '1.10.1'
REPOSITORY = 'https://github.com/betterleaks/betterleaks'
ARCHIVES = {
    'darwin_arm64': 'ca91eb3b006f15478411f235b5e2712fb15cea74f6701ebadc2364efe0af1403',
    'darwin_x64': '1ae2e3885d161918d8ad2e911e205e73f0d9ffba52c85b38126586c52d355ef4',
    'linux_arm64': '62a63199f9f61a6b5e5a6f58f048493db20fbc8c770014f4d903a4d97886e1bf',
    'linux_x64': 'c174b42d7aa60caf58c0c3e555c0e4bed01fe6b0d99a412bce777b5af4ce913e',
}


def archive_url(target):
    if target not in ARCHIVES: raise ValueError('Unsupported Betterleaks platform')
    return f'{REPOSITORY}/releases/download/v{VERSION}/betterleaks_{VERSION}_{target}.tar.gz'
