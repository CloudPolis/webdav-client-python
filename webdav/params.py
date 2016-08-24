"""Matrix parameter compiler."""

try:
    from urllib.parse import quote_plus
except ImportError:
    from urllib import quote_plus


def quote_path_with_matrix_params(path, matrix_params):
    """Compile a path and matrix parameter dict into a quoted URI path.

    >>> quote_path_with_matrix_params("/~parent/folder/file.txt" ,
    ...     {
    ...         "/~parent": {"a": ["1;", "2!"]},
    ...         "/~parent/folder/file.txt": {"i d": ["?"]},
    ...     },
    ... )
    '/%7Eparent;a=1%3B;a=2%21/folder/file.txt;i+d=%3F'
    """
    matrix_params = matrix_params or {}

    names = []
    components = []
    for name in path.split('/'):
        names.append(name)
        path_so_far = '/'.join(names)
        try:
            params = matrix_params[path_so_far]
        except KeyError:
            component = name
        else:
            path_params = []
            for key, values in sorted(params.items()):
                for value in values:
                    path_params.append(
                        ';{}={}'.format(quote_plus(key), quote_plus(value))
                    )
            component = '{}{}'.format(quote_plus(name), ''.join(path_params))
        components.append(component)
    return '/'.join(components)
