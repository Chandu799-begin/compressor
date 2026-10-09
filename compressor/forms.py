"""Django forms for uploads and compression options."""
from django import forms

from .models import CompressionJob
from .services.size_converter import build_presets
from .validators import validate_extension


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(item, initial) for item in data]
        return [single(data, initial)]


class UploadForm(forms.Form):
    files = MultipleFileField()

    def clean_files(self):
        files = self.cleaned_data.get("files", [])
        for uploaded in files:
            validate_extension(uploaded.name)
        return files


class CompressionOptionsForm(forms.Form):
    target_value = forms.FloatField(required=False, min_value=0)
    target_unit = forms.ChoiceField(choices=[("KB", "KB"), ("MB", "MB"), ("GB", "GB")], required=False)
    level = forms.ChoiceField(choices=CompressionJob.LEVEL_CHOICES, initial=CompressionJob.LEVEL_MEDIUM)
    max_width = forms.IntegerField(required=False, min_value=1)
    max_height = forms.IntegerField(required=False, min_value=1)
    keep_aspect = forms.BooleanField(required=False, initial=True)
    strip_metadata = forms.BooleanField(required=False)
    convert_to_webp = forms.BooleanField(required=False)
    output_format = forms.CharField(required=False)
    downsample = forms.BooleanField(required=False, initial=True)
    use_ghostscript = forms.BooleanField(required=False)

    def build_options(self):
        data = self.cleaned_data
        return {
            "max_width": data.get("max_width"),
            "max_height": data.get("max_height"),
            "keep_aspect": data.get("keep_aspect", True),
            "strip_metadata": data.get("strip_metadata", False),
            "convert_to_webp": data.get("convert_to_webp", False),
            "output_format": data.get("output_format") or "auto",
            "downsample": data.get("downsample", True),
            "use_ghostscript": data.get("use_ghostscript", False),
        }


def preset_context():
    return {"size_presets": build_presets()}
