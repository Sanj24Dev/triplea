from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "check_reachability_cpp",
        ["check_reachability.pyx"],
        language="c++",
        extra_compile_args=["-O3", "-std=c++11"],
    )
]

setup(
    name="check_reachability_cpp",
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': "3",
            'boundscheck': False,
            'wraparound': False,
        }
    ),
)