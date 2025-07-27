from setuptools import setup, find_packages

setup(
    name="minbackup",
    version="0.1.0",
    description="Minimalistic backup automation tool with VM snapshot support",
    author="Entro01",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "click>=8.0.0",
        "PyYAML>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "minbackup=minbackup.cli:main",
        ],
    },
    python_requires=">=3.8",
)