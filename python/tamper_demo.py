import os
import sys

from merkle import hash_dataset, build_tree, get_root


def main():
    data_folder = os.path.join(os.path.dirname(__file__), "..", "data")
    target_file = os.path.join(data_folder, "file1.txt")

    if not os.path.isfile(target_file):
        print(f"Error: '{target_file}' not found.")
        sys.exit(1)

    # hash original dataset
    print("\n" + "=" * 50)
    print("TAMPER DETECTION DEMO")
    print("=" * 50)

    file_hashes = hash_dataset(data_folder)
    leaf_hashes = [h for _, h in file_hashes]
    tree = build_tree(leaf_hashes)
    original_root = get_root(tree)

    print(f"\nOriginal Merkle root: {original_root}")

    # flip first byte of file1.txt
    with open(target_file, "rb") as f:
        original_data = f.read()

    tampered_data = bytes([original_data[0] ^ 0xFF]) + original_data[1:]

    with open(target_file, "wb") as f:
        f.write(tampered_data)

    print(f"\nTampered file1.txt:")
    print(f"  Original first byte: 0x{original_data[0]:02X} "
          f"('{chr(original_data[0])}')")
    print(f"  Tampered first byte: 0x{tampered_data[0]:02X}")

    # rehash tampered dataset
    tampered_hashes = hash_dataset(data_folder)
    tampered_leaves = [h for _, h in tampered_hashes]
    tampered_tree = build_tree(tampered_leaves)
    tampered_root = get_root(tampered_tree)

    print(f"\nTampered Merkle root: {tampered_root}")

    # compare
    print(f"\n{'=' * 50}")
    if original_root != tampered_root:
        print("TAMPER DETECTED!")
        print(f"  Original root: {original_root}")
        print(f"  Tampered root: {tampered_root}")
        print("  Roots don't match -- data was modified.")
    else:
        print("Roots match -- this shouldn't happen.")
    print("=" * 50)

    # restore original file
    with open(target_file, "wb") as f:
        f.write(original_data)

    print(f"\nRestored file1.txt to original state.")
    print("(Demo is repeatable)\n")


if __name__ == "__main__":
    main()
