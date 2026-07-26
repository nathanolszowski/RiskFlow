from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect

@login_required
def dashboard_test(request):
    return render(request, 'core/dashboard.html')

def toggle_theme(request):
    # Récupère le thème actuel depuis la session (défaut 'dark')
    current_theme = request.session.get('theme', 'dark')
    new_theme = 'light' if current_theme == 'dark' else 'dark'
    
    # Enregistre le nouveau thème en session
    request.session['theme'] = new_theme

    # Si la requête vient d'HTMX, on demande au navigateur de rafraîchir
    # ou on envoie l'en-tête HX-Refresh pour recharger proprement la page
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Refresh'] = 'true'
        return response

    return redirect(request.META.get('HTTP_REFERER', '/'))