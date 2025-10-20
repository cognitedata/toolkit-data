#!/usr/bin/env python3
"""
Checks structure and validates that all module paths exist.
Assumes "modules" as the base folder where packages.toml is located.
"""

import sys
from pathlib import Path
from typing import Any

import tomllib
from pydantic import BaseModel, Field, field_validator

MODULES_DIR = Path("modules")
PACKAGES_FILE = MODULES_DIR / "packages.toml"


class Library(BaseModel):
    """Library header section of packages.toml."""

    title: str = Field(min_length=1, description="Library title")
    description: str = Field(min_length=1, description="Library description")

    @field_validator("title", "description")
    @classmethod
    def validate_non_empty_string(cls, v: str) -> str:
        """Ensure strings are not just whitespace."""
        if not v.strip():
            raise ValueError("Must be a non-empty string")
        return v


class Package(BaseModel):
    """Individual package definition."""

    title: str = Field(min_length=1, description="Package title")
    id: str = Field(min_length=1, description="Package ID")
    description: str = Field(min_length=1, description="Package description")
    modules: list[str] = Field(min_length=1, description="List of module paths")
    canCherryPick: bool = Field(
        default=True, description="Whether modules can be cherry-picked"
    )

    @field_validator("title", "description", "id")
    @classmethod
    def validate_non_empty_string(cls, v: str) -> str:
        """Ensure strings are not just whitespace."""
        if not v.strip():
            raise ValueError("Must be a non-empty string")
        return v


class Module(BaseModel):
    """Module definition from module.toml."""

    id: str = Field(min_length=1, description="Module ID")
    package_id: str = Field(
        min_length=1, description="Package ID this module belongs to"
    )
    title: str = Field(min_length=1, description="Module title")
    is_selected_by_default: bool = Field(
        default=True, description="Whether module is selected by default"
    )


class ExtraResource(BaseModel):
    """Extra resource definition from module.toml."""

    location: str = Field(min_length=1, description="Relative path to extra resource")


class ModuleToml(BaseModel):
    """Full module.toml file structure."""

    module: Module
    extra_resources: list[ExtraResource] = Field(
        default_factory=list, description="Extra resources for the module"
    )


class PackagesToml(BaseModel):
    """Full packages.toml file structure."""

    library: Library
    packages: dict[str, Package] = Field(
        min_length=1, description="Dictionary of packages"
    )


class PackageValidator:
    """Validator for packages.toml and associated module files."""

    def __init__(self, base_path: Path = MODULES_DIR):
        """
        Initialize the validator.

        Args:
            base_path: Base directory where packages.toml and modules are located
        """
        self.base_path = base_path
        self.packages_file = base_path / "packages.toml"

    def load_packages_toml(self) -> dict[str, Any]:
        """Load and parse packages.toml file."""
        if not self.packages_file.exists():
            raise FileNotFoundError(f"ERROR: {self.packages_file} not found")

        try:
            with open(self.packages_file, "rb") as f:
                data = tomllib.load(f)
            print(f"✓ Successfully parsed {self.packages_file}")
            return data
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"ERROR: Invalid TOML format: {e}") from e

    def validate_module_path(self, package_name: str, module_path: str) -> None:
        """
        Validate that a module path exists and has a valid module.toml.

        Args:
            package_name: Name of the package containing the module
            module_path: Relative path to the module

        Raises:
            FileNotFoundError: If module path or module.toml doesn't exist
            ValueError: If module.toml is invalid
        """
        full_path = self.base_path / module_path
        if not full_path.exists():
            raise FileNotFoundError(
                f"ERROR: Package '{package_name}' module path '{module_path}' "
                f"does not exist at '{full_path}'"
            )

        module_toml_path = full_path / "module.toml"
        if not module_toml_path.exists():
            raise FileNotFoundError(
                f"ERROR: Package '{package_name}' module path '{module_path}' "
                f"does not have a module.toml file and is not a valid module"
            )

        # Load and validate module.toml
        try:
            with open(module_toml_path, "rb") as f:
                module_data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(
                f"ERROR: Package '{package_name}' module '{module_path}' "
                f"has invalid TOML in module.toml: {e}"
            ) from e

        # Validate module.toml structure using Pydantic
        try:
            module_toml = ModuleToml(**module_data)
        except Exception as e:
            raise ValueError(
                f"ERROR: Package '{package_name}' module '{module_path}' "
                f"has invalid module.toml structure: {e}"
            ) from e

        # Validate extra resources exist
        for extra_resource in module_toml.extra_resources:
            resource_path = self.base_path / extra_resource.location
            if not resource_path.exists():
                raise FileNotFoundError(
                    f"ERROR: Package '{package_name}' module '{module_path}' "
                    f"refers to a non-existent file: {resource_path}"
                )

        print(f"✓ Module '{module_path}' validated successfully")

    def validate_package_modules(self, package_name: str, package: Package) -> None:
        """
        Validate all modules in a package.

        Args:
            package_name: Name of the package
            package: Package model instance

        Raises:
            FileNotFoundError: If any module path is invalid
            ValueError: If any module.toml is invalid
        """
        for module_path in package.modules:
            self.validate_module_path(package_name, module_path)

    def validate(self) -> None:
        """
        Run full validation of packages.toml and all referenced modules.

        Raises:
            FileNotFoundError: If packages.toml or any module path is not found
            ValueError: If validation fails
        """
        # Check base path exists
        if not self.base_path.exists():
            raise FileNotFoundError(
                f"ERROR: Base path '{self.base_path}' does not exist"
            )

        # Load packages.toml
        data = self.load_packages_toml()

        # Validate using Pydantic model
        try:
            packages_toml = PackagesToml(**data)
        except Exception as e:
            raise ValueError(f"ERROR: Invalid packages.toml structure: {e}") from e

        print("✓ [library] header validation passed")
        print(f"✓ Found {len(packages_toml.packages)} packages")

        # Validate each package and its modules
        for package_name, package in packages_toml.packages.items():
            print(f"\nValidating package: {package_name}")
            print(f"✓ Package '{package_name}' structure validation passed")
            self.validate_package_modules(package_name, package)

        print(
            f"\n🎉 All validation checks passed! "
            f"{len(packages_toml.packages)} packages validated successfully."
        )


def main() -> None:
    """Main validation function."""
    try:
        validator = PackageValidator()
        validator.validate()
    except (FileNotFoundError, ValueError) as e:
        print(str(e))
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
