import hashlib
import os
import sys

# Setting the encoding for the system to UTF-8 to prevent string handling issues
# This is mainly a defense-in-depth measure.
# sys.setdefaultencoding('utf-8')

class Crypto:
    """
    A utility class for calculating SHA256 hashes of both files and strings.
    """

    @staticmethod
    def hash_file(filepath, blocksize=65536):
        """
        Calculates the SHA256 hash of a file's content. (Original implementation)

        :param filepath: The path to the file.
        :param blocksize: The size of chunks (in bytes) to read the file in.
        :return: The hexadecimal SHA256 digest string.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")

        hasher = hashlib.sha256()
        try:
            with open(filepath, 'rb') as afile:
                buf = afile.read(blocksize)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = afile.read(blocksize)
            return hasher.hexdigest()
        except IOError as e:
            print(f"Error reading file {filepath}: {e}")
            return None

    @staticmethod
    def hash_string(input_string, encoding='utf-8'):
        """
        Calculates the SHA256 hash of an input string. (The simple, correct implementation)

        This is the critical part. It must encode the string to bytes
        and update the hasher in a single, simple step.

        :param input_string: The string to be hashed.
        :param encoding: The encoding to use (default is UTF-8).
        :return: The hexadecimal SHA256 digest string.
        """
        if not isinstance(input_string, str):
            raise TypeError("Input must be a string.")

        hasher = hashlib.sha256()

        # CRITICAL: Encode the string to bytes
        hasher.update(input_string.encode(encoding))

        return hasher.hexdigest()