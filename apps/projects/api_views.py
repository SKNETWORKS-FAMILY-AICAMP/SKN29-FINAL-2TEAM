from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView
from rest_framework.views import APIView

from services.orchestration.analysis_run_service import create_analysis_run

from .models import AnalysisRun, Project
from .serializers import AnalysisRunSerializer, ProjectSerializer


class HealthAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "ai-project-operation-copilot"})


class ProjectListCreateAPIView(ListCreateAPIView):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.select_related("owner").all()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ProjectDetailAPIView(RetrieveAPIView):
    serializer_class = ProjectSerializer
    lookup_field = "project_id"
    queryset = Project.objects.select_related("owner").all()


class ProjectAnalysisRunAPIView(APIView):
    def post(self, request, project_id):
        project = get_object_or_404(Project, project_id=project_id)
        run = create_analysis_run(project=project, requested_by=request.user)
        return Response(AnalysisRunSerializer(run).data, status=status.HTTP_201_CREATED)


class AnalysisRunDetailAPIView(APIView):
    def get(self, request, run_id):
        run = get_object_or_404(AnalysisRun, run_id=run_id)
        return Response(AnalysisRunSerializer(run).data)
