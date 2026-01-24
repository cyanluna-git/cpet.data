import { useState, useCallback, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { api, type TestUploadAutoResponse } from "@/lib/api";
import { toast } from "sonner";
import {
  Upload,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ChevronDown,
  X,
  UserPlus,
  UserCheck,
} from "lucide-react";

interface TestUploadModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

type UploadState = "idle" | "uploading" | "success" | "error";

export function TestUploadModal({
  open,
  onClose,
  onSuccess,
}: TestUploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [result, setResult] = useState<TestUploadAutoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [calcMethod, setCalcMethod] = useState<"Frayn" | "Jeukendrup">("Frayn");
  const [smoothingWindow, setSmoothingWindow] = useState(10);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resetState = useCallback(() => {
    setFile(null);
    setUploadState("idle");
    setResult(null);
    setError(null);
  }, []);

  const handleClose = useCallback(() => {
    resetState();
    onClose();
  }, [resetState, onClose]);

  const handleFileSelect = useCallback((selectedFile: File | null) => {
    if (!selectedFile) return;

    // Validate file type
    const validExtensions = [".xlsx", ".xls"];
    const ext = selectedFile.name
      .toLowerCase()
      .slice(selectedFile.name.lastIndexOf("."));
    if (!validExtensions.includes(ext)) {
      toast.error(
        "지원하지 않는 파일 형식입니다. Excel 파일(.xlsx, .xls)만 업로드 가능합니다.",
      );
      return;
    }

    // Validate file size (50MB)
    if (selectedFile.size > 50 * 1024 * 1024) {
      toast.error("파일 크기가 50MB를 초과합니다.");
      return;
    }

    setFile(selectedFile);
    setError(null);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);

      const droppedFile = e.dataTransfer.files[0];
      handleFileSelect(droppedFile);
    },
    [handleFileSelect],
  );

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleUpload = async () => {
    if (!file) return;

    setUploadState("uploading");
    setError(null);

    try {
      const response = await api.uploadTestAuto(file, {
        calc_method: calcMethod,
        smoothing_window: smoothingWindow,
      });

      setResult(response);
      setUploadState("success");

      // Show toast with result
      if (response.subject_created) {
        toast.success(
          `새 피험자 "${response.subject_name}"가 생성되고 테스트가 업로드되었습니다.`,
        );
      } else {
        toast.success(
          `기존 피험자 "${response.subject_name}"에 테스트가 추가되었습니다.`,
        );
      }

      // Trigger table refresh
      onSuccess();
    } catch (err: any) {
      setUploadState("error");
      const errorMessage =
        err.response?.data?.detail ||
        err.message ||
        "업로드 중 오류가 발생했습니다.";
      setError(errorMessage);
      toast.error(errorMessage);
    }
  };

  const renderDropZone = () => (
    <div
      className={`
        border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors
        ${isDragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400"}
        ${file ? "border-green-500 bg-green-50" : ""}
      `}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={() => fileInputRef.current?.click()}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xls"
        className="hidden"
        onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
      />

      {file ? (
        <div className="flex flex-col items-center gap-2">
          <FileSpreadsheet className="w-12 h-12 text-green-600" />
          <p className="font-medium text-gray-900">{file.name}</p>
          <p className="text-sm text-gray-500">
            {(file.size / 1024 / 1024).toFixed(2)} MB
          </p>
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              setFile(null);
            }}
          >
            <X className="w-4 h-4 mr-1" />
            파일 제거
          </Button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2">
          <Upload className="w-12 h-12 text-gray-400" />
          <p className="font-medium text-gray-700">
            파일을 드래그하거나 클릭하여 선택하세요
          </p>
          <p className="text-sm text-gray-500">
            COSMED Excel 파일 (.xlsx, .xls) 지원
          </p>
        </div>
      )}
    </div>
  );

  const renderAdvancedSettings = () => (
    <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm" className="w-full justify-between">
          <span>고급 설정</span>
          <ChevronDown
            className={`w-4 h-4 transition-transform ${showAdvanced ? "rotate-180" : ""}`}
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-4 pt-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="calcMethod">계산 방법</Label>
            <Select
              value={calcMethod}
              onValueChange={(v) => setCalcMethod(v as "Frayn" | "Jeukendrup")}
            >
              <SelectTrigger id="calcMethod">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Frayn">Frayn (1983)</SelectItem>
                <SelectItem value="Jeukendrup">Jeukendrup (2005)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="smoothingWindow">평활화 윈도우</Label>
            <Input
              id="smoothingWindow"
              type="number"
              min={5}
              max={30}
              value={smoothingWindow}
              onChange={(e) =>
                setSmoothingWindow(parseInt(e.target.value) || 10)
              }
            />
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );

  const renderResult = () => {
    if (!result) return null;

    return (
      <div className="space-y-4">
        <div className="flex items-center justify-center gap-2 text-green-600">
          <CheckCircle2 className="w-8 h-8" />
          <span className="text-lg font-semibold">업로드 완료</span>
        </div>

        <div className="bg-gray-50 rounded-lg p-4 space-y-3">
          <div className="flex justify-between">
            <span className="text-gray-600">파일</span>
            <span className="font-medium">{result.source_filename}</span>
          </div>

          <div className="flex justify-between items-center">
            <span className="text-gray-600">피험자</span>
            <div className="flex items-center gap-2">
              {result.subject_created ? (
                <span className="inline-flex items-center gap-1 text-blue-600">
                  <UserPlus className="w-4 h-4" />
                  새로 생성됨
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-green-600">
                  <UserCheck className="w-4 h-4" />
                  기존 피험자
                </span>
              )}
              <span className="font-medium">{result.subject_name}</span>
            </div>
          </div>

          <div className="flex justify-between">
            <span className="text-gray-600">상태</span>
            <span
              className={`font-medium ${
                result.parsing_status === "success"
                  ? "text-green-600"
                  : result.parsing_status === "warning"
                    ? "text-yellow-600"
                    : "text-red-600"
              }`}
            >
              {result.parsing_status === "success"
                ? "파싱 성공"
                : result.parsing_status === "warning"
                  ? "경고 있음"
                  : result.parsing_status}
            </span>
          </div>

          {result.parsing_warnings && result.parsing_warnings.length > 0 && (
            <div className="pt-2 border-t">
              <p className="text-sm text-yellow-600 font-medium mb-1">경고:</p>
              <ul className="text-sm text-yellow-700 list-disc list-inside">
                {result.parsing_warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          )}

          {result.parsing_errors && result.parsing_errors.length > 0 && (
            <div className="pt-2 border-t">
              <p className="text-sm text-red-600 font-medium mb-1">오류:</p>
              <ul className="text-sm text-red-700 list-disc list-inside">
                {result.parsing_errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderError = () => {
    if (!error) return null;

    return (
      <div className="flex flex-col items-center gap-4 p-6">
        <AlertCircle className="w-12 h-12 text-red-500" />
        <p className="text-center text-red-600 font-medium">{error}</p>
        <Button variant="outline" onClick={resetState}>
          다시 시도
        </Button>
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>테스트 데이터 업로드</DialogTitle>
          <DialogDescription>
            COSMED Excel 파일을 업로드하면 피험자를 자동으로 매칭하거나
            생성합니다.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          {uploadState === "idle" && (
            <div className="space-y-4">
              {renderDropZone()}
              {renderAdvancedSettings()}
            </div>
          )}

          {uploadState === "uploading" && (
            <div className="flex flex-col items-center gap-4 py-8">
              <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
              <p className="text-gray-600">파일 처리 중...</p>
              <p className="text-sm text-gray-500">
                피험자 매칭 및 데이터 파싱 중입니다.
              </p>
            </div>
          )}

          {uploadState === "success" && renderResult()}
          {uploadState === "error" && renderError()}
        </div>

        <DialogFooter>
          {uploadState === "idle" && (
            <>
              <Button variant="outline" onClick={handleClose}>
                취소
              </Button>
              <Button onClick={handleUpload} disabled={!file}>
                <Upload className="w-4 h-4 mr-2" />
                업로드
              </Button>
            </>
          )}

          {uploadState === "success" && (
            <Button onClick={handleClose}>확인</Button>
          )}

          {uploadState === "error" && (
            <Button variant="outline" onClick={handleClose}>
              닫기
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
