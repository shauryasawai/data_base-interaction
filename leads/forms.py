from django import forms
from .models import Lead

class LeadUploadForm(forms.Form):
    file = forms.FileField(
        label='Upload Excel File',
        help_text='Upload an Excel file (.xlsx or .xls) with lead data',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx,.xls'
        })
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            if not file.name.endswith(('.xlsx', '.xls')):
                raise forms.ValidationError('Only Excel files (.xlsx, .xls) are allowed')
            if file.size > 10 * 1024 * 1024:  # 10MB limit
                raise forms.ValidationError('File size must be under 10MB')
        return file


class LeadSearchForm(forms.Form):
    skills = forms.CharField(
        label='Required Skills',
        help_text='Enter comma-separated skills to match',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'e.g., Marketing Strategy, SEO, SEM, Public Relations (PR), Content Development'
        })
    )




class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = ['name', 'email', 'phone', 'role', 'company', 'linkedin_url', 
                  'location', 'skills', 'experience_years', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Data Scientist, AI Engineer'}),
            'company': forms.TextInput(attrs={'class': 'form-control'}),
            'linkedin_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://linkedin.com/in/...'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Hyderabad, India'}),
            'skills': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter comma-separated skills'
            }),
            'experience_years': forms.NumberInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }