using UnrealBuildTool;

public class YgoAREditorTarget : TargetRules
{
	public YgoAREditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("YgoAR");
	}
}
