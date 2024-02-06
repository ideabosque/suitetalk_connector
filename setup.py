"""
# SuiteTalk-Connector
=====================

"""

from setuptools import find_packages, setup

setup(
    name="SuiteTalk-Connector",
    version="0.0.4",
    url="https://github.com/ideabosque/suitetalk_connector",
    license="MIT",
    author="Idea Bosque",
    author_email="ideabosque@gmail.com",
    description="Use to connect NetSuite SuiteTalk SOAP API.",
    long_description=__doc__,
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    platforms="any",
    install_requires=["zeep", "tenacity", "requests", "warlock"],
    keywords=[
        "DataWald",
        "NetSuite",
        "SuiteTalk",
        "Integration",
        "API",
    ],  # arbitrary keywords
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Environment :: Web Environment",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
