import hashlib


def get_file_hash(filename, hash_name='sha256', buf_size=65535):
    hash = hashlib.new(hash_name)
    with open(filename, 'rb') as f:
        for data in iter(lambda: f.read(buf_size), b''):
            hash.update(data)
    return hash.hexdigest()
