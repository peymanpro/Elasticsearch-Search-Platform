"""
Presentation layer.

Responsible for translating HTTP requests into calls on the application
layer, and for rendering the application layer's results back into HTTP
responses. This layer may depend on Django and Django REST Framework, and
on the application layer. It must not depend on infrastructure directly.
"""
