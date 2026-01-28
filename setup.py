"""
Setup script to build Lightning Dictation as a proper macOS app using py2app.
Run with: python setup.py py2app
"""

from setuptools import setup

APP = ['dictate_native.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,
    'plist': {
        'CFBundleName': 'Lightning Dictation',
        'CFBundleDisplayName': 'Lightning Dictation',
        'CFBundleIdentifier': 'com.local.lightningdictation',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': False,
        'NSMicrophoneUsageDescription': 'Lightning Dictation needs microphone access to transcribe your speech.',
        'NSAppleEventsUsageDescription': 'Lightning Dictation needs accessibility access to type transcribed text.',
    },
    'packages': [
        'rumps',
        'mlx_whisper',
        'mlx',
        'sounddevice',
        'numpy',
        'pynput',
        'pyperclip',
        'huggingface_hub',
    ],
    'includes': [
        'Foundation',
        'AppKit',
        'objc',
        'PyObjCTools',
    ],
    'iconfile': 'Lightning Dictation.app/Contents/Resources/AppIcon.icns',
}

setup(
    app=APP,
    name='Lightning Dictation',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
