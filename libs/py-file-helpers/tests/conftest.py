import pytest
from pathlib import Path
from PIL import Image

@pytest.fixture
def mock_image_path(tmp_path: Path) -> Path:
    """
    Fixture that creates a temporary, valid, empty JPEG file 
    for testing EXIF extraction functions.
    
    The file is created in a temporary directory managed by pytest.
    """
    # Define the path for the mock file within the temporary directory
    file_path = tmp_path / "mock_test_image.jpg"
    
    try:
        # Create a simple, 1x1 black image using PIL/Pillow
        img = Image.new('RGB', (1, 1), color = 'black')
        
        # Save it as a JPEG file
        img.save(file_path, 'jpeg')
        
        # Ensure the file exists before yielding the path
        if not file_path.exists():
            raise FileNotFoundError("Mock image failed to save.")
            
        yield file_path
        
    finally:
        # PIL/Pillow resources are closed when 'with Image.new' block exits
        pass

@pytest.fixture
def corrupted_file_path(tmp_path: Path) -> Path:
    """
    Fixture that creates a file that exists but is not a valid image format,
    which can trigger PIL's UnidentifiedImageError or similar issues.
    """
    file_path = tmp_path / "corrupted_file.txt"
    # Write some garbage data that PIL definitely won't recognize as a JPEG
    with open(file_path, "w") as f:
        f.write("This is not an image file.")
    yield file_path